import { useEffect, useState } from "react";
import { useAppState, useActions, useAppDispatch } from "../../state/AppContext";
import * as api from "../../data/client";
import { adaptAnalyticsResults } from "../../data/analyticsAdapter";
import { formatReportPeriod } from "../../utils/format";
import { cn } from "@/lib/utils";
import { ContentContainer } from "../layout";
import { Button } from "@/components/ui/button";
import AccessibleModulesList from "./AccessibleModulesList";
import ConnectZohoPanel from "./ConnectZohoPanel";
import DepthSelector from "./DepthSelector";
import ClockToggle from "./ClockToggle";
import { DateRangeField, DateRangePresets, RANGE_LABELS } from "./DateRangePicker";
import CostEstimate from "./CostEstimate";
import LoadingState from "../shared/LoadingState";

function SetupStep({ step, title, lede, last = false, children }) {
  const headingId = `setup-step-${step}-title`;
  const index = String(step).padStart(2, "0");
  return (
    <section
      className="grid min-w-0 grid-cols-[2.5rem_minmax(0,1fr)] gap-x-5 sm:grid-cols-[3rem_minmax(0,1fr)] sm:gap-x-7"
      aria-labelledby={headingId}
    >
      <div className="relative flex flex-col items-center" aria-hidden="true">
        <span className="font-heading text-xl font-semibold tracking-tight text-brand sm:text-2xl">
          {index}
        </span>
        {!last && (
          <span className="mt-3 w-px flex-1 bg-line" />
        )}
      </div>
      <div className={cn("min-w-0", last ? "pb-2" : "pb-12 sm:pb-16")}>
        <h2
          id={headingId}
          className="font-heading text-xl font-semibold tracking-tight text-ink sm:text-2xl"
        >
          {title}
        </h2>
        {lede && (
          <p className="mt-1.5 max-w-[52ch] text-sm leading-relaxed text-ink-soft">
            {lede}
          </p>
        )}
        <div className="mt-6 flex min-w-0 flex-col gap-6">{children}</div>
      </div>
    </section>
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

function orgInitials(label) {
  const parts = String(label || "")
    .split(/\s+/)
    .filter(Boolean);
  if (parts.length >= 2) {
    return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  }
  return String(label || "ZH").slice(0, 2).toUpperCase();
}

export default function SetupScreen() {
  const { connection, scanConfig, connectionNotice, scanHistory } = useAppState();
  const { setScanConfig } = useActions();
  const dispatch = useAppDispatch();
  const [estimate, setEstimate] = useState(null);
  const [estimating, setEstimating] = useState(false);
  const [starting, setStarting] = useState(false);
  const [connecting, setConnecting] = useState(false);

  // Default module selection to everything accessible, once the connection loads.
  useEffect(() => {
    if (Array.isArray(connection?.accessibleModules) && scanConfig.modules.length === 0) {
      setScanConfig({
        modules: connection.accessibleModules
          .filter((module) => Number(module.recordCount) > 0)
          .map((module) => module.apiName),
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connection]);

  useEffect(() => {
    if (!scanConfig.modules.length) {
      setEstimate(null);
      return;
    }
    let cancelled = false;
    setEstimating(true);
    api.estimateScan(scanConfig).then((result) => {
      if (!cancelled) {
        setEstimate(result);
        setEstimating(false);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [scanConfig.modules, scanConfig.depth]);

  useEffect(() => {
    if (connecting) {
      window.location.assign(api.ZOHO_CONSENT_URL);
    }
  }, [connecting]);

  function handleConnect() {
    setConnecting(true);
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

  if (connection === "loading") {
    return (
      <ContentContainer className="flex min-h-0 w-full flex-1 flex-col py-8">
        <LoadingState label="Checking your connection" />
      </ContentContainer>
    );
  }

  if (connecting) {
    return (
      <ContentContainer className="flex min-h-0 w-full flex-1 flex-col py-8">
        <LoadingState label="Redirecting to Zoho" />
      </ContentContainer>
    );
  }

  if (!connection) {
    return (
      <ContentContainer className="flex min-h-full flex-col justify-center py-12 sm:py-16">
        <ConnectZohoPanel onConnect={handleConnect} connecting={connecting} notice={connectionNotice} />
      </ContentContainer>
    );
  }

  function toggleModule(apiName) {
    const module = connection.accessibleModules.find(
      (candidate) => candidate.apiName === apiName
    );
    if (!module || Number(module.recordCount) <= 0) return;
    const set = new Set(scanConfig.modules);
    set.has(apiName) ? set.delete(apiName) : set.add(apiName);
    setScanConfig({ modules: Array.from(set) });
  }

  function selectAllModules(selectAll) {
    setScanConfig({
      modules: selectAll
        ? connection.accessibleModules
            .filter((module) => Number(module.recordCount) > 0)
            .map((module) => module.apiName)
        : [],
    });
  }

  async function handleStart() {
    setStarting(true);
    try {
      const createdScan = await api.startScan(scanConfig);
      if (createdScan.reused && createdScan.status === "COMPLETED") {
        const results = await api.getScanResults(createdScan.scanId);
        dispatch({
          type: "scanComplete",
          scanId: createdScan.scanId,
          scan: {
            ...adaptAnalyticsResults(results),
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

  const organizationLabel =
    connection.organizationName || connection.organizationId || "Zoho CRM";
  const connectedName =
    connection.connectedUser?.name || connection.connectedUser?.email;
  const moduleCount = scanConfig.modules.length;
  const canStart = moduleCount > 0 && !starting;

  return (
    <ContentContainer className="flex min-h-full min-w-0 flex-col pt-8 sm:pt-10">
      <p className="max-w-[40rem] text-sm leading-relaxed text-ink-soft">
        Three decisions, then a read-only pass over what this login can see.
        Nothing in Zoho is created, updated, or deleted.
      </p>

      <div className="mt-10 min-w-0 flex-1 sm:mt-12">
        <SetupStep
          step={1}
          title="Who, and how deep"
          lede="The connected org is fixed for this run. Depth caps how many records we read in each module."
        >
          <div className="flex items-start gap-4">
            <div
              className="grid size-11 shrink-0 place-items-center bg-brand-soft font-heading text-sm font-semibold tracking-wide text-brand-strong"
              aria-hidden="true"
            >
              {orgInitials(organizationLabel)}
            </div>
            <div className="min-w-0">
              <p className="font-heading text-lg font-semibold tracking-tight text-ink">
                {organizationLabel}
              </p>
              {connectedName && (
                <p className="mt-0.5 text-[13px] text-ink-soft">
                  Connected as {connectedName}. Visibility follows this login,
                  not the whole org.
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
        </SetupStep>

        <SetupStep
          step={2}
          title="Which records count"
          lede="Period is the window. Clock is whether we use created time or last modified time."
        >
          <DateRangePresets
            value={scanConfig.range}
            onChange={(range) => setScanConfig({ range })}
          />
          {scanConfig.range?.id === "custom" && (
            <DateRangeField
              value={scanConfig.range}
              onChange={(range) => setScanConfig({ range })}
            />
          )}
          <ClockToggle
            value={scanConfig.clock}
            onChange={(clock) => setScanConfig({ clock })}
          />
        </SetupStep>

        <SetupStep
          step={3}
          title="What to include"
          lede="Only modules visible under this Zoho login are listed. A small count usually means profile visibility, not an empty module."
          last
        >
          <AccessibleModulesList
            modules={connection.accessibleModules}
            selected={scanConfig.modules}
            onToggle={toggleModule}
            onSelectAll={selectAllModules}
          />
        </SetupStep>
      </div>

      <div className="sticky bottom-0 z-20 -mx-[var(--app-gutter)] mt-8 border-t border-line bg-[color-mix(in_srgb,var(--paper)_92%,transparent)] px-[var(--app-gutter)] py-4 backdrop-blur-md">
        <div className="flex min-w-0 flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <dl className="m-0 grid min-w-0 flex-1 grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
            <DockStat label="Modules">
              {moduleCount} {moduleCount === 1 ? "module" : "modules"}
            </DockStat>
            <DockStat label="Period">{periodSummary(scanConfig.range)}</DockStat>
            <CostEstimate estimate={estimate} loading={estimating} />
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
