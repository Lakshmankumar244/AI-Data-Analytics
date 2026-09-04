import { useEffect, useState } from "react";
import { useAppState, useActions, useAppDispatch } from "../../state/AppContext";
import * as api from "../../data/client";
import { adaptAnalyticsResults } from "../../data/analyticsAdapter";
import { formatReportPeriod } from "../../utils/format";
import { ContentContainer, PageHeader } from "../layout";
import AccessibleModulesList from "./AccessibleModulesList";
import ConnectZohoPanel from "./ConnectZohoPanel";
import DepthSelector from "./DepthSelector";
import ClockToggle from "./ClockToggle";
import { DateRangeField, DateRangePresets, RANGE_LABELS } from "./DateRangePicker";
import CostEstimate from "./CostEstimate";
import LoadingState from "../shared/LoadingState";
import "./SetupScreen.css";

function SetupSection({ step, title, children }) {
  const headingId = `setup-step-${step}-title`;
  return (
    <section className="panel setup-section" aria-labelledby={headingId}>
      <header className="setup-section-header">
        <span className="setup-step-index" aria-hidden="true">
          {step}
        </span>
        <h2 id={headingId} className="section-heading">
          {title}
        </h2>
      </header>
      <div className="setup-section-body">{children}</div>
    </section>
  );
}

function periodSummary(range) {
  const resolved = formatReportPeriod(range?.from, range?.to);
  if (resolved) return resolved;
  if (range?.id && RANGE_LABELS[range.id]) return RANGE_LABELS[range.id];
  if (range?.id === "custom") return "Custom range";
  return range?.id || "Period not set";
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
    return <LoadingState label="Checking your connection" />;
  }

  if (connecting) {
    return <LoadingState label="Redirecting to Zoho" />;
  }

  if (!connection) {
    return (
      <ContentContainer className="setup-screen">
        <PageHeader
          title="Check your data health"
          description="Connect your Zoho account to see what your login can access."
        />
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

  return (
    <ContentContainer className="setup-screen">
      <div className="setup-workspace">
        <SetupSection step={1} title="Org and depth">
          <div className="setup-field-row">
            <div className="setup-field">
              <p className="eyebrow">Client org</p>
              <div className="setup-field-control setup-field-control-readonly">
                {organizationLabel}
              </div>
              {connectedName && (
                <p className="setup-org-meta">
                  Connected as <strong>{connectedName}</strong>. This scans only
                  what your account can see in Zoho CRM.
                </p>
              )}
              <button
                type="button"
                className="setup-connect-another"
                onClick={handleConnect}
                disabled={connecting}
              >
                + Connect to another organization
              </button>
            </div>
            <DepthSelector
              value={scanConfig.depth}
              onChange={(depth) => setScanConfig({ depth })}
            />
          </div>
        </SetupSection>

        <SetupSection step={2} title="Period">
          <DateRangePresets
            value={scanConfig.range}
            onChange={(range) => setScanConfig({ range })}
          />
          <div className="setup-field-row">
            <DateRangeField
              value={scanConfig.range}
              onChange={(range) => setScanConfig({ range })}
            />
            <ClockToggle
              value={scanConfig.clock}
              onChange={(clock) => setScanConfig({ clock })}
            />
          </div>
        </SetupSection>

        <SetupSection step={3} title="Modules">
          <AccessibleModulesList
            modules={connection.accessibleModules}
            selected={scanConfig.modules}
            onToggle={toggleModule}
            onSelectAll={selectAllModules}
          />
        </SetupSection>

        <section className="panel setup-summary" aria-labelledby="setup-summary-title">
          <header className="setup-section-header">
            <h2 id="setup-summary-title" className="section-heading">
              Scan summary
            </h2>
          </header>
          <div className="setup-summary-bar">
            <p className="setup-summary-facts">
              <span>
                {moduleCount} {moduleCount === 1 ? "module" : "modules"}
              </span>
              <span className="setup-summary-sep" aria-hidden="true">
                |
              </span>
              <span>{periodSummary(scanConfig.range)}</span>
              <span className="setup-summary-sep" aria-hidden="true">
                |
              </span>
              <CostEstimate estimate={estimate} loading={estimating} />
            </p>
            <div className="setup-actions">
              {scanHistory.length > 0 && (
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={starting}
                  onClick={() => dispatch({ type: "showHome" })}
                >
                  Back to reports
                </button>
              )}
              <button
                type="button"
                className="btn btn-primary"
                disabled={!scanConfig.modules.length || starting}
                onClick={handleStart}
              >
                {starting ? "Starting\u2026" : "Start scan"}
              </button>
            </div>
          </div>
          <p className="cost-estimate-scope">
            Read-only access. Nothing in your CRM is changed by running this scan.
          </p>
        </section>
      </div>
    </ContentContainer>
  );
}
