import { useEffect, useState } from "react";
import { useAppState, useActions, useAppDispatch } from "../../state/AppContext";
import * as api from "../../data/client";
import { adaptAnalyticsResults } from "../../data/analyticsAdapter";
import { ContentContainer, PageHeader, ResponsiveGrid } from "../layout";
import AccessibleModulesList from "./AccessibleModulesList";
import ConnectZohoPanel from "./ConnectZohoPanel";
import DepthSelector from "./DepthSelector";
import ClockToggle from "./ClockToggle";
import DateRangePicker from "./DateRangePicker";
import CostEstimate from "./CostEstimate";
import LoadingState from "../shared/LoadingState";
import "./SetupScreen.css";

const ZOHO_CONSENT_URL =
  "https://ai-data-analytics-60083091023.development.catalystserverless.in/server/ai_data_analytics_function/api/zoho/consent";

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
      window.location.assign(ZOHO_CONSENT_URL);
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

  return (
    <ContentContainer className="setup-screen">
      <PageHeader title="Check your data health">
        <p className="page-header-description">
          Connected as <strong>{connection.connectedUser.name}</strong>. This scans
          only what your account can see in Zoho CRM.
        </p>
      </PageHeader>

      <ResponsiveGrid min="360px" gap="var(--sp-5)" className="setup-grid">
        <section className="panel">
          <AccessibleModulesList
            modules={connection.accessibleModules}
            selected={scanConfig.modules}
            onToggle={toggleModule}
            onSelectAll={selectAllModules}
          />
        </section>

        <section className="panel">
          <DepthSelector
            value={scanConfig.depth}
            onChange={(depth) => setScanConfig({ depth })}
          />
        </section>

        <section className="panel setup-panel-row">
          <ClockToggle value={scanConfig.clock} onChange={(clock) => setScanConfig({ clock })} />
          <DateRangePicker value={scanConfig.range} onChange={(range) => setScanConfig({ range })} />
        </section>

        <section className="panel">
          <CostEstimate estimate={estimate} loading={estimating} />
        </section>
      </ResponsiveGrid>

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
          {starting ? "Starting\u2026" : "Run scan"}
        </button>
      </div>
    </ContentContainer>
  );
}
