import { useEffect, useState } from "react";
import { useAppDispatch, useAppState } from "../../state/AppContext";
import { adaptAnalyticsResults } from "../../data/analyticsAdapter";
import { activateConnection, getScanHistory, getScanResults, ZOHO_CONSENT_URL } from "../../data/client";
import { formatNumber } from "../../utils/format";
import { ContentContainer, PageHeader } from "../layout";
import Band from "../shared/Band";
import Dropdown from "../shared/Dropdown";
import LoadingState from "../shared/LoadingState";
import "./HomeScreen.css";

const COMPLETED_BAND = {
  id: "completed",
  label: "COMPLETED",
  color: "var(--strong)",
  soft: "var(--strong-soft)",
};

function readableDate(value) {
  if (!value) return "—";
  const normalized = String(value).replace(
    /^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})(?::\d{3})?/,
    "$1T$2"
  );
  const date = new Date(normalized);
  return Number.isNaN(date.getTime())
    ? String(value)
    : new Intl.DateTimeFormat("en-IN", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(date);
}

function ModuleSummary({ modules }) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? modules : modules.slice(0, 3);
  const remaining = modules.length - visible.length;
  return (
    <div className="history-modules">
      <span>{visible.join(", ") || "—"}</span>
      {modules.length > 3 && (
        <button
          type="button"
          className="history-modules-toggle"
          onClick={() => setExpanded((current) => !current)}
        >
          {expanded ? "Show less" : `+ ${remaining} more`}
        </button>
      )}
    </div>
  );
}

export default function HomeScreen() {
  const { connection, scanHistory, connectionNotice, historyNeedsRefresh } = useAppState();
  const dispatch = useAppDispatch();
  const [openingScanId, setOpeningScanId] = useState(null);
  const [error, setError] = useState(null);
  const [switchingConnection, setSwitchingConnection] = useState(false);
  const [historyConnectionId, setHistoryConnectionId] = useState("all");

  const historyConnections = Array.from(
    new Map(
      scanHistory
        .filter((scan) => scan.connection?.connectionId)
        .map((scan) => [scan.connection.connectionId, scan.connection])
    ).values()
  ).sort((left, right) =>
    (left.organizationName || left.name || left.email || left.organizationId).localeCompare(
      right.organizationName || right.name || right.email || right.organizationId
    )
  );
  const visibleScans =
    historyConnectionId === "all"
      ? scanHistory
      : scanHistory.filter(
          (scan) => scan.connection?.connectionId === historyConnectionId
        );

  useEffect(() => {
    if (!historyNeedsRefresh) return undefined;
    let cancelled = false;
    getScanHistory()
      .then((history) => {
        if (!cancelled) {
          dispatch({ type: "historyLoaded", scanHistory: history?.scans ?? [] });
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "History could not be refreshed");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [dispatch, historyNeedsRefresh]);

  async function openReport(scan) {
    if (scan.status !== "COMPLETED" || !scan.hasResults) return;
    setOpeningScanId(scan.scanId);
    setError(null);
    try {
      const results = await getScanResults(scan.scanId);
      dispatch({
        type: "scanComplete",
        scanId: scan.scanId,
        scan: { ...adaptAnalyticsResults(results), reportContext: scan },
        refreshHistory: false,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "The report could not be opened");
    } finally {
      setOpeningScanId(null);
    }
  }

  function resumeScan(scan) {
    dispatch({
      type: "scanStarted",
      scanId: scan.scanId,
      scanContext: scan,
      scanConfigPatch: {
        modules: scan.modules,
        depth: scan.depth,
        clock: scan.clock === "Modified_Time" ? "modified" : "created",
        range: {
          id: "custom",
          from: scan.fromUtc || null,
          to: scan.toUtc || null,
        },
      },
    });
  }

  async function selectConnection(connectionId) {
    if (!connectionId || connectionId === connection?.connectionId) return;
    setSwitchingConnection(true);
    setError(null);
    try {
      const selected = await activateConnection(connectionId);
      dispatch({ type: "connectionLoaded", connection: selected });
    } catch (err) {
      setError(err instanceof Error ? err.message : "The Zoho account could not be selected");
    } finally {
      setSwitchingConnection(false);
    }
  }

  if (connection === "loading") {
    return (
      <ContentContainer className="home-screen">
        <LoadingState label="Restoring your account" />
      </ContentContainer>
    );
  }

  return (
    <ContentContainer className="home-screen">
      <PageHeader
        eyebrow="Data health"
        title="Reports and scans"
        description={
          connection
            ? `Connected to ${connection.organizationName || "Zoho CRM"} as ${connection.connectedUser.name || connection.connectedUser.email}.`
            : "Connect Zoho CRM to start a new scan."
        }
        actions={
          connection ? (
            <>
              {connection.availableConnections?.length > 1 && (
                <Dropdown
                  label="New scans use"
                  value={connection.connectionId}
                  onChange={selectConnection}
                  disabled={switchingConnection}
                  options={connection.availableConnections.map((item) => ({
                    id: item.connectionId,
                    label: item.organizationName
                      ? `${item.organizationName} · ${item.name || item.email}`
                      : item.name || item.email || item.organizationId,
                  }))}
                />
              )}
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => window.location.assign(ZOHO_CONSENT_URL)}
              >
                Connect another Zoho account
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => dispatch({ type: "showSetup" })}
              >
                New scan
              </button>
            </>
          ) : (
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => dispatch({ type: "showSetup" })}
            >
              Connect Zoho CRM
            </button>
          )
        }
      />

      {connectionNotice && <p className="home-notice">{connectionNotice}</p>}

      <section className="panel history-panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">History</p>
            <h2>Past scans</h2>
          </div>
          <div className="history-tools">
            {historyConnections.length > 1 && (
              <Dropdown
                label="Show reports from"
                value={historyConnectionId}
                onChange={setHistoryConnectionId}
                options={[
                  { id: "all", label: "All accounts" },
                  ...historyConnections.map((item) => ({
                    id: item.connectionId,
                    label: item.organizationName
                      ? `${item.organizationName} · ${item.name || item.email}`
                      : item.name || item.email || item.organizationId,
                  })),
                ]}
              />
            )}
            <span className="history-count mono">
              {visibleScans.length}
              {historyConnectionId !== "all" ? ` / ${scanHistory.length}` : ""}
            </span>
          </div>
        </div>

        {error && <p className="home-error" role="alert">{error}</p>}
        {visibleScans.length === 0 ? (
          <p className="history-empty">
            {scanHistory.length === 0
              ? "No scans have been created for this user yet."
              : "No scans have been created with this Zoho account."}
          </p>
        ) : (
          <div className="history-table-wrap">
            <table className="history-table">
              <thead>
                <tr>
                  <th>Created</th>
                  <th>Zoho account</th>
                  <th>Modules</th>
                  <th>Records</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {visibleScans.map((scan) => {
                  const canOpen = scan.status === "COMPLETED" && scan.hasResults;
                  const canResume = !["COMPLETED", "FAILED_TERMINAL"].includes(scan.status);
                  return (
                    <tr key={scan.scanId}>
                      <td>{readableDate(scan.createdAt)}</td>
                      <td>
                        <span className="history-account-name">
                          {scan.connection?.organizationName ||
                            scan.connection?.name ||
                            scan.connection?.email ||
                            "Unknown account"}
                        </span>
                        {(scan.connection?.organizationName ||
                          (scan.connection?.name && scan.connection?.email)) && (
                          <span className="history-account-email">
                            {scan.connection.organizationName
                              ? [scan.connection.name, scan.connection.email]
                                  .filter(Boolean)
                                  .join(" · ")
                              : scan.connection.email}
                          </span>
                        )}
                      </td>
                      <td><ModuleSummary modules={scan.modules} /></td>
                      <td className="mono">{formatNumber(scan.recordCount)}</td>
                      <td>
                        {scan.status === "COMPLETED" ? (
                          <Band band={COMPLETED_BAND} />
                        ) : (
                          <span className={`history-status history-status-${String(scan.status).toLowerCase()}`}>
                            {scan.status}
                          </span>
                        )}
                      </td>
                      <td className="history-action">
                        {canOpen && (
                          <button
                            type="button"
                            className="btn btn-secondary"
                            disabled={openingScanId === scan.scanId}
                            onClick={() => openReport(scan)}
                          >
                            {openingScanId === scan.scanId ? "Opening…" : "Open report"}
                          </button>
                        )}
                        {canResume && (
                          <button
                            type="button"
                            className="btn btn-secondary"
                            onClick={() => resumeScan(scan)}
                          >
                            Resume
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </ContentContainer>
  );
}
