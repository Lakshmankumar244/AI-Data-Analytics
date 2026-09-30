import { useEffect, useRef } from "react";
import { AppProvider, useAppState, useAppDispatch } from "./state/AppContext";
import * as api from "./data/client";
import { AppShell as Shell, ContentContainer, MainContent } from "./components/layout";
import ErrorState from "./components/shared/ErrorState";
import SetupScreen from "./components/setup/SetupScreen";
import ConnectScreen from "./components/setup/ConnectScreen";
import RunningScreen from "./components/running/RunningScreen";
import ReportShell from "./components/report/ReportShell";
import HomeScreen from "./components/home/HomeScreen";
import LoadingState from "./components/shared/LoadingState";
import {
  dispatchResolved,
  navigateTo,
  parseLocation,
  resolveRoute,
  routeFromState,
} from "./navigation";
import { captureMarketplaceEntry } from "./data/marketplaceEntry";

function AppShell() {
  const state = useAppState();
  const dispatch = useAppDispatch();
  const stateRef = useRef(state);
  stateRef.current = state;

  useEffect(() => {
    let cancelled = false;
    const params = new URLSearchParams(window.location.hash.slice(1));
    const returningFromZoho = params.get("zoho_connected") === "1";
    const zohoError = params.get("zoho_error");
    const returningFromSalesforce = params.get("salesforce_connected") === "1";
    const salesforceError = params.get("salesforce_error");

    // OAuth callback markers are one-time signals. Removing them means a
    // later reload starts a new connection flow instead of restoring this one.
    if (returningFromZoho || zohoError || returningFromSalesforce || salesforceError) {
      params.delete("zoho_connected");
      params.delete("zoho_error");
      params.delete("salesforce_connected");
      params.delete("salesforce_error");
      const remainingHash = params.toString();
      window.history.replaceState(
        {},
        "",
        `${window.location.pathname}${window.location.search}${
          remainingHash ? `#${remainingHash}` : ""
        }`
      );
    }

    const notice = zohoError
      ? zohoError === "ZOHO_CONSENT_DECLINED"
        ? "Connection wasn't changed. You can try again anytime."
        : "Zoho connection failed. Your previous reports are still available."
      : returningFromZoho
      ? "Zoho CRM connection updated."
      : null;
    const salesforceNotice = salesforceError
      ? salesforceError === "SALESFORCE_CONSENT_DECLINED"
        ? "Connection wasn't changed. You can try again anytime."
        : "Salesforce connection failed. You can try again anytime."
      : returningFromSalesforce
      ? "Salesforce CRM connection updated."
      : null;

    async function restoreSession() {
      try {
        const [connection, salesforceConnection, history] = await Promise.all([
          api.getConnection(),
          api.getSalesforceConnection().catch(() => null),
          api.getScanHistory(),
        ]);
        const scans = history?.scans ?? [];
        let resolved;
        try {
          resolved = await resolveRoute(parseLocation(), scans);
        } catch (routeErr) {
          if (routeErr?.status === 401 || routeErr?.status === 403) throw routeErr;
          if (routeErr?.status === 404) {
            resolved = { phase: "home", urlRoute: { name: "home" } };
          } else {
            throw routeErr;
          }
        }
        if (cancelled) return;
        if (returningFromSalesforce || salesforceError) {
          resolved = { phase: "connect", urlRoute: { name: "connect" } };
        }
        if (resolved.urlRoute) navigateTo(resolved.urlRoute, { replace: true });
        dispatchResolved(dispatch, resolved, {
          session: true,
          connection,
          salesforceConnection,
          scans,
          notice:
            notice ||
            (connection?.legacyMigrated
              ? "Your previous development reports were migrated to this Catalyst account."
              : null),
          salesforceNotice,
        });
      } catch (err) {
        if (cancelled) return;
        if (err?.status === 401 || err?.status === 403) {
          captureMarketplaceEntry();
          window.location.assign(`${window.location.origin}/__catalyst/auth/login`);
          return;
        }
        dispatch({ type: "error", message: err.message });
      }
    }

    restoreSession();
    return () => {
      cancelled = true;
    };
  }, [dispatch]);

  useEffect(() => {
    let generation = 0;
    async function onPopState() {
      const gen = ++generation;
      try {
        const resolved = await resolveRoute(
          parseLocation(),
          stateRef.current.scanHistory ?? []
        );
        if (gen !== generation) return;
        if (resolved.urlRoute) navigateTo(resolved.urlRoute, { replace: true });
        dispatchResolved(dispatch, resolved);
      } catch (err) {
        if (gen !== generation) return;
        if (err?.status === 401 || err?.status === 403) {
          captureMarketplaceEntry();
          window.location.assign(`${window.location.origin}/__catalyst/auth/login`);
          return;
        }
        if (err?.status === 404) {
          navigateTo({ name: "home" }, { replace: true });
          dispatch({ type: "showHome" });
          return;
        }
        dispatch({ type: "error", message: err.message });
      }
    }
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, [dispatch]);

  useEffect(() => {
    if (state.phase === "boot" || state.phase === "error") return;
    const route = routeFromState(state.phase, state.scanId);
    if (route) navigateTo(route);
  }, [state.phase, state.scanId]);

  return (
    <Shell>
      <MainContent>
        {state.phase === "setup" && <SetupScreen />}
        {state.phase === "connect" && <ConnectScreen />}
        {state.phase === "home" && <HomeScreen />}
        {state.phase === "running" && <RunningScreen />}
        {state.phase === "report" && <ReportShell />}
        {/* The two transient states get the same content column as every
            screen so they do not sit flush against the rail. */}
        {state.phase === "boot" && (
          <ContentContainer className="flex min-h-0 w-full flex-1 flex-col py-[var(--sp-6)]">
            <LoadingState label="Restoring your account" />
          </ContentContainer>
        )}
        {state.phase === "error" && (
          <ContentContainer className="py-[var(--sp-6)]">
            <ErrorState
              message={state.errorMessage}
              onRetry={() => dispatch({ type: "reset" })}
            />
          </ContentContainer>
        )}
      </MainContent>
    </Shell>
  );
}

export default function App() {
  return (
    <AppProvider>
      <AppShell />
    </AppProvider>
  );
}
