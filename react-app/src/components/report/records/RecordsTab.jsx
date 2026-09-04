import { useEffect, useMemo, useState } from "react";
import { useAppState, useActions } from "../../../state/AppContext";
import * as api from "../../../data/client";
import { stateMeta } from "../../../utils/bands";
import { formatNumber } from "../../../utils/format";
import { groupOwnerAnalytics, recordOwnerQueryKeys } from "../../../data/ownerAnalytics";
import Band from "../../shared/Band";
import LoadingState from "../../shared/LoadingState";
import "./RecordsTab.css";

const SUPPORTED_STATES = new Set(["incomplete", "inaccurate"]);
const RECORD_FILTERS = [
  { id: "proper", label: "Clean" },
  { id: "incomplete", label: "Missing information" },
  { id: "inaccurate", label: "Wrong values" },
  { id: "suspicious", label: "Looks fabricated" },
  { id: "suspected_duplicate", label: "Possible duplicate" },
  { id: "confirmed_duplicate", label: "Certain duplicate" },
];

function formatDate(iso) {
  if (!iso) return "N/A";
  return new Date(iso).toLocaleDateString("en-IN", { year: "numeric", month: "short", day: "numeric" });
}

function recordTitle(record) {
  const moduleName = String(record?.module || "").trim().toLowerCase();
  const candidates = [record?.recordName, record?.recordRef];
  for (const candidate of candidates) {
    const name = String(candidate || "").trim();
    if (name && name.toLowerCase() !== moduleName && name !== "Record") return name;
  }
  return "Unnamed record";
}

function matchesActiveState(record, activeState) {
  if (!activeState) return true;
  if (!SUPPORTED_STATES.has(activeState)) return false;
  return record.state === activeState;
}

export default function RecordsTab() {
  const { scanId, scan, scanConfig, focusState, filterModules, filterUsers } = useAppState();
  const { setFilter } = useActions();
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [data, setData] = useState(null);
  const [tableLoading, setTableLoading] = useState(true);
  const [error, setError] = useState(null);
  const activeState = RECORD_FILTERS.some((state) => state.id === focusState)
    ? focusState
    : null;
  const scanDepth = scan?.reportContext?.depth || scanConfig.depth || "quick";
  const listedCounts = data?.summary?.stateCounts;
  const scanCleanCount = Number(scan?.stateBreakdown?.proper);

  useEffect(() => {
    setPage(1);
  }, [focusState, filterModules, filterUsers, submittedQuery]);

  useEffect(() => {
    const timer = window.setTimeout(() => setSubmittedQuery(query.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    let cancelled = false;
    setTableLoading(true);
    setError(null);
    const owners = groupOwnerAnalytics(scan?.moduleAnalytics ?? [], []);
    const filters = {
      states: activeState ? [activeState] : [],
      modules: filterModules,
      owners: recordOwnerQueryKeys(owners, filterUsers),
      q: submittedQuery,
    };
    api.getRecords(scanId, filters, page)
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setTableLoading(false);
      })
      .catch((requestError) => {
        if (cancelled) return;
        setError(requestError.message);
        setTableLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [scanId, scan, activeState, filterModules, filterUsers, page, submittedQuery]);

  const rows = useMemo(
    () => (data?.records ?? []).filter((record) => matchesActiveState(record, activeState)),
    [activeState, data]
  );

  const emptyHint = useMemo(() => {
    if (activeState === "proper") {
      return Number.isFinite(scanCleanCount) && scanCleanCount > 0
        ? `${formatNumber(scanCleanCount)} clean records were counted in this scan. They are not stored as a list — only flagged findings are kept for investigation.`
        : "Clean records are not listed. Only flagged findings are stored for investigation.";
    }
    if (activeState && !SUPPORTED_STATES.has(activeState)) {
      return "This classification is not stored on the current scan yet.";
    }
    if (activeState) {
      return "No records match the selected state and module filters.";
    }
    if (scanDepth === "quick") {
      return "Quick scans exclude optional missing fields. Those blanks may still affect completeness.";
    }
    return "No records matched the finding rules for this scan depth.";
  }, [activeState, scanCleanCount, scanDepth]);

  const inScopeCount = activeState
    ? Number(listedCounts?.[activeState] || 0)
    : Number(listedCounts?.listedRecordCount ?? data?.summary?.storedSampleCount ?? 0);
  const showSampleNote =
    data?.summary?.measured &&
    Number(data.summary.affectedRecordCount) > Number(data.summary.storedSampleCount || 0);

  return (
    <div className="records-tab">
      <section className="panel records-panel">
        <div className="panel-header records-panel-header">
          <p className="eyebrow">Records</p>
        </div>
        <div className="records-state-tabs" role="tablist" aria-label="Filter by record state">
          {RECORD_FILTERS.map((state) => {
            const meta = stateMeta(state.id);
            const isActive = activeState === state.id;
            const count = listedCounts
              ? Number(listedCounts[state.id] || 0)
              : null;
            return (
              <button
                key={state.id}
                type="button"
                role="tab"
                aria-selected={isActive}
                className={`records-state-tab${isActive ? " records-state-tab-active" : ""}`}
                style={isActive ? { borderTopColor: meta?.color || "var(--brand)" } : undefined}
                onClick={() => setFilter({ focusState: isActive ? null : state.id })}
              >
                <span>{state.label}</span>
                <strong className="mono">
                  {count === null ? "—" : formatNumber(count)}
                </strong>
              </button>
            );
          })}
        </div>

        <div className="records-toolbar">
          <form
            className="records-search"
            onSubmit={(event) => {
              event.preventDefault();
              setSubmittedQuery(query.trim());
            }}
          >
            <input
              type="search"
              value={query}
              placeholder="Search records..."
              aria-label="Search records"
              onChange={(event) => setQuery(event.target.value)}
            />
          </form>
        </div>

        {showSampleNote && (
          <p className="records-sample-note">
            Showing up to {formatNumber(data.summary.storedSampleCount)} representative
            flagged records from {formatNumber(data.summary.affectedRecordCount)} detected.
          </p>
        )}

        {error ? (
          <div className="records-message records-error">{error}</div>
        ) : tableLoading || !data ? (
          <LoadingState label="Loading records" />
        ) : !data.summary?.measured ? (
          <div className="records-message">
            Record-level findings were not measured in this scan. Run a new scan after deploying this feature.
          </div>
        ) : (
          <>
            <div className="records-table-wrap">
              <table className="records-table">
                <thead>
                  <tr>
                    <th>Record</th>
                    <th>Module</th>
                    <th>State</th>
                    <th>What's wrong</th>
                    <th>Owner</th>
                    <th>Detected</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.length === 0 && (
                    <tr>
                      <td colSpan={6} className="records-empty">
                        <div className="records-empty-state">
                          <strong>No matching records</strong>
                          <span>{emptyHint}</span>
                        </div>
                      </td>
                    </tr>
                  )}
                  {rows.map((record) => (
                    <tr key={record.findingId}>
                      <td>
                        <span className="records-name">{recordTitle(record)}</span>
                      </td>
                      <td>{record.module}</td>
                      <td>
                        <Band band={stateMeta(record.state)} size="sm" />
                      </td>
                      <td>
                        <div>{record.reason}</div>
                        {record.issues?.length > 0 && (
                          <div className="records-fields">
                            {record.issues.slice(0, 4).map((issue) => issue.fieldLabel || issue.fieldApiName).join(", ")}
                            {record.issues.length > 4 ? ` +${record.issues.length - 4} more` : ""}
                          </div>
                        )}
                      </td>
                      <td>{record.ownerName}</td>
                      <td className="mono">{formatDate(record.computedAt)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="records-pagination">
              <span className="records-pagination-count">
                {formatNumber(inScopeCount)} record{inScopeCount === 1 ? "" : "s"} in this view
              </span>
              <div className="records-pagination-controls">
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={page <= 1}
                  onClick={() => setPage((current) => current - 1)}
                >
                  Previous
                </button>
                <span className="mono records-pagination-page">
                  Page {page}
                </span>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={!data.hasMore || rows.length === 0}
                  onClick={() => setPage((current) => current + 1)}
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
