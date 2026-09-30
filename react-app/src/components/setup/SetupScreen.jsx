import { useEffect, useMemo, useState } from "react";
import { useAppState, useActions, useAppDispatch } from "../../state/AppContext";
import * as api from "../../data/client";
import {
  defaultAccessibleModuleNames,
  isSalesforceProvider,
  isZohoProvider,
  retainedAccessibleModules,
  salesforceAccessibleModules,
  salesforceOrganizationName,
} from "../../data/scanSetup";
import { formatReportPeriod } from "../../utils/format";
import { ContentContainer } from "../layout";
import { Button } from "@/components/ui/button";
import AccessibleModulesList from "./AccessibleModulesList";
import DepthSelector from "./DepthSelector";
import ClockToggle from "./ClockToggle";
import { DateRangeField, DateRangePresets, RANGE_LABELS } from "./DateRangePicker";
import CostEstimate from "./CostEstimate";
import LoadingState from "../shared/LoadingState";

function SetupSection({ step, title, children }) {
  const headingId = `setup-step-${step}-title`;
  const index = String(step).padStart(2, "0");
  return (
    <section
      className="min-w-0 rounded-md border border-line bg-surface p-5 @min-[640px]:p-6"
      aria-labelledby={headingId}
    >
      <h2
        id={headingId}
        className="flex min-w-0 items-baseline gap-3 font-heading text-xl font-semibold tracking-tight text-ink sm:text-2xl"
      >
        <span className="font-heading text-brand" aria-hidden="true">
          {index}
        </span>
        {title}
      </h2>
      <div className="mt-6 min-w-0">{children}</div>
    </section>
  );
}

function SetupColumns({ children }) {
  return (
    <div className="grid min-w-0 grid-cols-1 items-start gap-6 @min-[640px]:grid-cols-2 @min-[640px]:gap-x-10">
      {children}
    </div>
  );
}

function DockStat({ label, children }) {
  return (
    <div className="min-w-0">
      <p className="eyebrow">{label}</p>
      <p className="mt-1 text-[13px] font-medium text-ink">{children}</p>
    </div>
  );
}

function periodSummary(range) {
  const resolved = formatReportPeriod(range?.from, range?.to);
  if (resolved) return resolved;
  if (range?.id && RANGE_LABELS[range.id]) return RANGE_LABELS[range.id];
  if (range?.id === "custom") return "Custom range";
  return range?.id || "Period not set";
}

function orgInitials(label, fallback = "ZH") {
  const parts = String(label || "")
    .split(/\s+/)
    .filter(Boolean);
  if (parts.length >= 2) {
    return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  }
  return String(label || fallback).slice(0, 2).toUpperCase();
}

export default function SetupScreen() {
  const {
    connection,
    salesforceConnection,
    scanConfig,
    scanHistory,
    activeConnection,
  } = useAppState();
  const { setScanConfig } = useActions();
  const dispatch = useAppDispatch();
  const [estimate, setEstimate] = useState(null);
  const [estimating, setEstimating] = useState(false);
  const [starting, setStarting] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [salesforceMetadata, setSalesforceMetadata] = useState(null);
  const [metadataError, setMetadataError] = useState(null);
  const [loadingMetadata, setLoadingMetadata] = useState(false);

  const isSalesforce = isSalesforceProvider(activeConnection);
  const isZoho = isZohoProvider(activeConnection);
  const sessionLoading =
    connection === "loading" || salesforceConnection === "loading";
  const accessibleModules = useMemo(
    () =>
      isSalesforce
        ? salesforceAccessibleModules(salesforceMetadata)
        : (connection?.accessibleModules ?? []),
    [isSalesforce, salesforceMetadata, connection]
  );

  useEffect(() => {
    if (isSalesforce) return;
    if (Array.isArray(connection?.accessibleModules) && scanConfig.modules.length === 0) {
      setScanConfig({
        modules: connection.accessibleModules.map((module) => module.apiName),
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connection, isSalesforce]);

  useEffect(() => {
    if (!isSalesforce) {
      setSalesforceMetadata(null);
      setMetadataError(null);
      setLoadingMetadata(false);
      return undefined;
    }
    let cancelled = false;
    setLoadingMetadata(true);
    setMetadataError(null);
    api
      .getSalesforceMetadata()
      .then((metadata) => {
        if (cancelled) return;
        setSalesforceMetadata(metadata);
      })
      .catch((err) => {
        if (cancelled) return;
        setSalesforceMetadata(null);
        setMetadataError(
          err instanceof Error
            ? err.message
            : "Salesforce metadata could not be loaded"
        );
      })
      .finally(() => {
        if (!cancelled) setLoadingMetadata(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isSalesforce, activeConnection?.connectionId]);

  useEffect(() => {
    if (!isSalesforce || !salesforceMetadata) return;
    const modules = salesforceAccessibleModules(salesforceMetadata);
    const retained = retainedAccessibleModules(scanConfig.modules, modules);
    if (retained.length === 0) {
      setScanConfig({ modules: defaultAccessibleModuleNames(modules) });
      return;
    }
    if (retained.length !== scanConfig.modules.length) {
      setScanConfig({ modules: retained });
    }
    // Sync once when Salesforce metadata arrives so persisted Zoho names are
    // not posted. Do not re-run when the user clears the selection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isSalesforce, salesforceMetadata]);

  useEffect(() => {
    if (!scanConfig.modules.length) {
      setEstimate(null);
      setEstimating(false);
      return;
    }
    setEstimate(api.estimateScan(scanConfig, accessibleModules));
    setEstimating(false);
  }, [accessibleModules, scanConfig]);

  useEffect(() => {
    if (sessionLoading) return;
    if (activeConnection) return;
    dispatch({ type: "showConnect" });
  }, [sessionLoading, activeConnection, dispatch]);

  useEffect(() => {
    if (connecting && isSalesforce) {
      window.location.assign(api.SALESFORCE_CONSENT_URL);
    }
  }, [connecting, isSalesforce]);

  function handleConnect() {
    setConnecting(true);
    if (!isSalesforce) {
      window.location.assign(api.zohoConsentUrl());
    }
    // Full-page redirect - this navigates away, it doesn't resolve in place.
    // Route it through your own backend endpoint (recommended: keeps the
    // OAuth client secret and redirect_uri server-side, and lets you set
    // the CSRF `state` param securely), e.g.:
    //   window.location.href = "/api/zoho/consent";
    // Zoho then redirects back to your callback route, which exchanges the
    // code for a token, stores the connection, and sends the user back
    // here. Whatever already populates `connection` in AppContext (likely
    // an api.getConnection() call on app boot) will then resolve with the
    // real accessibleModules for this user - not the mock's fixed
    // Leads/Contacts/Deals/Accounts list.
  }

  if (sessionLoading) {
    return (
      <ContentContainer className="flex min-h-0 w-full flex-1 flex-col py-8">
        <LoadingState label="Checking your connection" />
      </ContentContainer>
    );
  }

  if (connecting) {
    return (
      <ContentContainer className="flex min-h-0 w-full flex-1 flex-col py-8">
        <LoadingState
          label={isSalesforce ? "Redirecting to Salesforce" : "Redirecting to Zoho"}
        />
      </ContentContainer>
    );
  }

  if (!activeConnection || (isZoho && !connection)) {
    return (
      <ContentContainer className="flex min-h-0 w-full flex-1 flex-col py-8">
        <LoadingState label="Checking your connection" />
      </ContentContainer>
    );
  }

  if (isSalesforce && loadingMetadata && !salesforceMetadata) {
    return (
      <ContentContainer className="flex min-h-0 w-full flex-1 flex-col py-8">
        <LoadingState label="Loading Salesforce metadata" />
      </ContentContainer>
    );
  }

  function toggleModule(apiName) {
    const module = accessibleModules.find(
      (candidate) => candidate.apiName === apiName
    );
    if (!module) return;
    const set = new Set(scanConfig.modules);
    set.has(apiName) ? set.delete(apiName) : set.add(apiName);
    setScanConfig({ modules: Array.from(set) });
  }

  function selectAllModules(selectAll) {
    setScanConfig({
      modules: selectAll ? defaultAccessibleModuleNames(accessibleModules) : [],
    });
  }

  async function handleStart() {
    setStarting(true);
    try {
      const createdScan = await api.startScan(scanConfig);
      if (createdScan.reused && createdScan.status === "COMPLETED") {
        const scorecard = await api.getScorecard(createdScan.scanId);
        dispatch({
          type: "scanComplete",
          scanId: createdScan.scanId,
          scan: {
            ...scorecard,
            reportContext: createdScan.reportContext,
            reuseNotice:
              "No CRM changes were found for this scope. Showing the latest matching report.",
          },
          refreshHistory: false,
        });
      } else {
        dispatch({
          type: "scanStarted",
          scanId: createdScan.scanId,
          scanContext: createdScan.reportContext ?? null,
        });
      }
    } catch (err) {
      dispatch({
        type: "error",
        message: err instanceof Error ? err.message : "The scan could not be created",
      });
    } finally {
      setStarting(false);
    }
  }

  const organizationLabel = isSalesforce
    ? salesforceOrganizationName(
        salesforceMetadata,
        activeConnection.organizationName || "Salesforce"
      )
    : connection.organizationName || connection.organizationId || "Zoho CRM";
  const connectedName = isSalesforce
    ? activeConnection.connectedUser?.name || activeConnection.connectedUser?.email
    : connection.connectedUser?.name || connection.connectedUser?.email;
  const moduleCount = scanConfig.modules.length;
  const canStart =
    moduleCount > 0 && !starting && !(isSalesforce && loadingMetadata);

  return (
    <ContentContainer className="flex min-h-full min-w-0 flex-col pt-6 @min-[640px]:pt-8">
      <div className="mt-2 flex min-w-0 flex-1 flex-col gap-4 @min-[640px]:gap-5">
        <SetupSection step={1} title="Org and depth">
          <SetupColumns>
            <div className="flex min-w-0 items-start gap-4">
              <div
                className="grid size-11 shrink-0 place-items-center bg-brand-soft font-heading text-sm font-semibold tracking-wide text-brand-strong"
                aria-hidden="true"
              >
                {orgInitials(organizationLabel, isSalesforce ? "SF" : "ZH")}
              </div>
              <div className="min-w-0">
                <p className="font-heading text-lg font-semibold tracking-tight text-ink">
                  {organizationLabel}
                </p>
                {connectedName && (
                  <p className="mt-0.5 text-[13px] text-ink-soft">
                    Connected as {connectedName}
                  </p>
                )}
                <Button
                  type="button"
                  variant="link"
                  className="mt-1 h-auto px-0 text-[13px]"
                  onClick={handleConnect}
                  disabled={connecting}
                >
                  Connect another organization
                </Button>
              </div>
            </div>
            <DepthSelector
              value={scanConfig.depth}
              onChange={(depth) => setScanConfig({ depth })}
            />
          </SetupColumns>
        </SetupSection>

        <SetupSection step={2} title="Period">
          <SetupColumns>
            <div className="flex min-w-0 flex-col gap-6">
              <DateRangePresets
                value={scanConfig.range}
                onChange={(range) => setScanConfig({ range })}
              />
              <DateRangeField
                value={scanConfig.range}
                onChange={(range) => setScanConfig({ range })}
              />
            </div>
            <ClockToggle
              value={scanConfig.clock}
              onChange={(clock) => setScanConfig({ clock })}
            />
          </SetupColumns>
        </SetupSection>

        <SetupSection step={3} title="Modules">
          {metadataError ? (
            <p className="mb-4 text-[13px] text-risk" role="alert">
              {metadataError}
            </p>
          ) : null}
          <AccessibleModulesList
            modules={accessibleModules}
            selected={scanConfig.modules}
            onToggle={toggleModule}
            onSelectAll={selectAllModules}
          />
        </SetupSection>
      </div>

      <div className="sticky bottom-0 z-20 -mx-[var(--app-gutter)] mt-8 border-t border-line bg-[color-mix(in_srgb,var(--paper)_92%,transparent)] px-[var(--app-gutter)] py-4 backdrop-blur-md">
        <div className="flex min-w-0 flex-col gap-4 @min-[640px]:flex-row @min-[640px]:items-end @min-[640px]:justify-between">
          <dl className="m-0 grid min-w-0 flex-1 grid-cols-2 gap-x-6 gap-y-3 @min-[640px]:grid-cols-4">
            <DockStat label="Modules">
              {moduleCount} {moduleCount === 1 ? "module" : "modules"}
            </DockStat>
            <DockStat label="Period">{periodSummary(scanConfig.range)}</DockStat>
            <CostEstimate
              estimate={estimate}
              loading={estimating}
              showApiCredits={!isSalesforce}
            />
          </dl>
          <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
            {scanHistory.length > 0 && (
              <Button
                type="button"
                variant="ghost"
                size="lg"
                disabled={starting}
                onClick={() => dispatch({ type: "showHome" })}
              >
                Back to reports
              </Button>
            )}
            <Button
              type="button"
              size="lg"
              className="min-w-[9.5rem]"
              disabled={!canStart}
              onClick={handleStart}
            >
              {starting ? "Starting\u2026" : "Start scan"}
            </Button>
          </div>
        </div>
      </div>
    </ContentContainer>
  );
}
