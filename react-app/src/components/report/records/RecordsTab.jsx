import { useEffect, useMemo, useState } from "react";
import { useAppState, useActions } from "../../../state/AppContext";
import * as api from "../../../data/client";
import { stateMeta } from "../../../utils/bands";
import { formatNumber } from "../../../utils/format";
import { groupOwnerAnalytics, recordOwnerQueryKeys } from "../../../data/ownerAnalytics";
import Band from "../../shared/Band";
import LoadingState from "../../shared/LoadingState";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

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
    <div className="flex min-w-0 flex-col py-4 pb-12 @max-[640px]:pb-8">
      <section className="min-w-0">
        <header className="mb-2.5">
          <p className="eyebrow">Records</p>
        </header>

        <div
          className="mb-3 grid grid-cols-6 gap-x-4 gap-y-3 @max-[900px]:grid-cols-3 @max-[640px]:grid-cols-2"
          role="tablist"
          aria-label="Filter by record state"
        >
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
                className={cn(
                  "m-0 flex min-w-0 cursor-pointer flex-col items-start gap-1 border-r-0 border-b-0 border-l-0 border-t-[3px] bg-transparent p-0 pt-2 pb-1 text-left font-[inherit]",
                  isActive ? "text-ink-soft" : "text-ink-muted"
                )}
                style={{
                  borderTopColor: isActive
                    ? meta?.color || "var(--brand)"
                    : "transparent",
                }}
                onClick={() => setFilter({ focusState: isActive ? null : state.id })}
              >
                <span className="text-[10px] font-bold tracking-wide uppercase">
                  {state.label}
                </span>
                <strong className="mono text-lg font-semibold tracking-tight text-ink">
                  {count === null ? "—" : formatNumber(count)}
                </strong>
              </button>
            );
          })}
        </div>

        <div className="mb-2.5 flex justify-end @max-[640px]:justify-stretch">
          <form
            className="min-w-0 @max-[640px]:w-full"
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
              className="min-h-[34px] w-[min(280px,100%)] border border-line bg-surface px-2.5 py-1.5 text-[13px] text-ink placeholder:text-ink-muted @max-[640px]:w-full"
            />
          </form>
        </div>

        {showSampleNote && (
          <p className="mb-2.5 text-[11px] leading-normal text-brand-strong">
            Showing up to {formatNumber(data.summary.storedSampleCount)} representative
            flagged records from {formatNumber(data.summary.affectedRecordCount)} detected.
          </p>
        )}

        {error ? (
          <p className="text-[13px] leading-normal text-risk" role="alert">
            {error}
          </p>
        ) : tableLoading || !data ? (
          <LoadingState label="Loading records" />
        ) : !data.summary?.measured ? (
          <p className="max-w-[46ch] text-[13px] leading-normal text-ink-soft">
            Record-level findings were not measured in this scan. Run a new scan after deploying this feature.
          </p>
        ) : (
          <>
            <div className="min-w-0 overflow-x-auto">
              <table className="w-full border-separate border-spacing-0 text-xs">
                <thead>
                  <tr>
                    {["Record", "Module", "State", "What's wrong", "Owner", "Detected"].map(
                      (heading) => (
                        <th
                          key={heading}
                          className="border-b border-line px-2.5 py-2 text-left text-[10px] font-bold tracking-wider whitespace-nowrap text-ink-muted uppercase"
                        >
                          {heading}
                        </th>
                      )
                    )}
                  </tr>
                </thead>
                <tbody className="[&>tr:last-child>td]:border-b-0">
                  {rows.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-0 py-10">
                        <div className="flex flex-col gap-1.5">
                          <strong className="text-[15px] font-semibold text-ink">
                            No matching records
                          </strong>
                          <span className="max-w-[440px] text-xs text-ink-muted">
                            {emptyHint}
                          </span>
                        </div>
                      </td>
                    </tr>
                  )}
                  {rows.map((record) => (
                    <tr
                      key={record.findingId}
                      className="[&:not(:only-child)]:hover:bg-surface-sunken"
                    >
                      <td className="border-b border-line px-2.5 py-1.5 align-middle">
                        <span className="text-[13px] font-semibold text-ink">
                          {recordTitle(record)}
                        </span>
                      </td>
                      <td className="border-b border-line px-2.5 py-1.5 align-middle">
                        {record.module}
                      </td>
                      <td className="border-b border-line px-2.5 py-1.5 align-middle">
                        <Band band={stateMeta(record.state)} size="sm" />
                      </td>
                      <td className="border-b border-line px-2.5 py-1.5 align-middle">
                        <div>{record.reason}</div>
                        {record.issues?.length > 0 && (
                          <div className="mt-0.5 text-[11px] text-ink-muted">
                            {record.issues.slice(0, 4).map((issue) => issue.fieldLabel || issue.fieldApiName).join(", ")}
                            {record.issues.length > 4 ? ` +${record.issues.length - 4} more` : ""}
                          </div>
                        )}
                      </td>
                      <td className="border-b border-line px-2.5 py-1.5 align-middle">
                        {record.ownerName}
                      </td>
                      <td className="mono border-b border-line px-2.5 py-1.5 align-middle">
                        {formatDate(record.computedAt)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mt-3 flex items-center justify-between gap-4 @max-[640px]:flex-col @max-[640px]:items-start">
              <span className="text-xs text-ink-muted">
                {formatNumber(inScopeCount)} record{inScopeCount === 1 ? "" : "s"} in this view
              </span>
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage((current) => current - 1)}
                >
                  Previous
                </Button>
                <span className="mono text-xs text-ink-muted">
                  Page {page}
                </span>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={!data.hasMore || rows.length === 0}
                  onClick={() => setPage((current) => current + 1)}
                >
                  Next
                </Button>
              </div>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
