import { useEffect, useState } from "react";
import { useAppState, useActions } from "../../../state/AppContext";
import * as api from "../../../data/client";
import { RECORD_STATES, stateMeta } from "../../../utils/bands";
import { formatNumber } from "../../../utils/format";
import Band from "../../shared/Band";
import LoadingState from "../../shared/LoadingState";
import "./RecordsTab.css";

const SUPPORTED_STATES = new Set(["incomplete", "inaccurate"]);

function formatDate(iso) {
  if (!iso) return "N/A";
  return new Date(iso).toLocaleDateString("en-IN", { year: "numeric", month: "short", day: "numeric" });
}

export default function RecordsTab() {
  const { scanId, scan, scanConfig, focusState, filterModules } = useAppState();
  const { setFilter } = useActions();
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const activeState = SUPPORTED_STATES.has(focusState) ? focusState : null;
  const scanDepth = scan?.reportContext?.depth || scanConfig.depth || "quick";

  // Any filter change resets to page 1 - a stale page number past the end
  // of a newly-filtered result set would just render an empty table.
  useEffect(() => {
    setPage(1);
  }, [focusState, filterModules]);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    const filters = { states: activeState ? [activeState] : [], modules: filterModules };
    api.getRecords(scanId, filters, page)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((requestError) => {
        if (!cancelled) setError(requestError.message);
      });
    return () => {
      cancelled = true;
    };
  }, [scanId, activeState, filterModules, page]);

  return (
    <div className="records-tab">
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Records</p>
            <h1>Flagged records</h1>
          </div>
          {data?.summary?.measured && (
            <div className="records-header-count">
              <strong>{formatNumber(data.summary.affectedRecordCount)}</strong>
              <span>actionable</span>
            </div>
          )}
        </div>

        <div className="records-state-filter" role="group" aria-label="Filter by state">
          <button
            type="button"
            className={`chip${!activeState ? " chip-active" : ""}`}
            aria-pressed={!activeState}
            onClick={() => setFilter({ focusState: null })}
          >
            All
          </button>
          {RECORD_STATES.filter((s) => SUPPORTED_STATES.has(s.id)).map((s) => (
            <button
              key={s.id}
              type="button"
              className={`chip${activeState === s.id ? " chip-active" : ""}`}
              aria-pressed={activeState === s.id}
              onClick={() => setFilter({ focusState: activeState === s.id ? null : s.id })}
            >
              {s.label}
            </button>
          ))}
        </div>

        <p className="records-disclosure">
          Completeness and validity findings only. CRM field values and record IDs are not displayed.
        </p>
        {data?.summary?.schemaVersion === "record-findings-v3" &&
          data.summary.affectedRecordCount > data.summary.storedSampleCount && (
            <p className="records-sample-note">
              Showing up to {formatNumber(data.summary.storedSampleCount)} representative
              flagged records from {formatNumber(data.summary.affectedRecordCount)} detected.
              Totals and Fix recommendations include every finding.
            </p>
          )}

        {error ? (
          <div className="records-message records-error">{error}</div>
        ) : !data ? (
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
                  {data.records.length === 0 && (
                    <tr>
                      <td colSpan={6} className="records-empty">
                        <div className="records-empty-state">
                          <span className="records-empty-icon" aria-hidden="true">✓</span>
                          <strong>No actionable issues found</strong>
                          <span>
                            {activeState
                              ? "No records match the selected state and module filters."
                              : scanDepth === "quick"
                              ? "Quick scans exclude optional missing fields. Those blanks may still affect completeness."
                              : "No records matched the finding rules for this scan depth."}
                          </span>
                        </div>
                      </td>
                    </tr>
                  )}
                  {data.records.map((r) => (
                    <tr key={r.findingId}>
                      <td className="mono records-id">{r.recordRef}</td>
                      <td>{r.module}</td>
                      <td>
                        <Band band={stateMeta(r.state)} size="sm" />
                      </td>
                      <td>
                        <div>{r.reason}</div>
                        {r.issues?.length > 0 && (
                          <div className="records-fields">
                            {r.issues.slice(0, 4).map((issue) => issue.fieldLabel || issue.fieldApiName).join(", ")}
                            {r.issues.length > 4 ? ` +${r.issues.length - 4} more` : ""}
                          </div>
                        )}
                      </td>
                      <td>{r.ownerName}</td>
                      <td className="mono">{formatDate(r.computedAt)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="records-pagination">
              <span className="records-pagination-count">
                {data.summary.schemaVersion === "record-findings-v3"
                  ? `${formatNumber(data.summary.storedSampleCount)} samples stored · ${formatNumber(data.summary.affectedRecordCount)} total flagged`
                  : `${formatNumber(data.summary.affectedRecordCount)} flagged record${data.summary.affectedRecordCount === 1 ? "" : "s"} in scope`}
              </span>
              <div className="records-pagination-controls">
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => p - 1)}
                >
                  Previous
                </button>
                <span className="mono records-pagination-page">
                  Page {page}
                </span>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={!data.hasMore}
                  onClick={() => setPage((p) => p + 1)}
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
