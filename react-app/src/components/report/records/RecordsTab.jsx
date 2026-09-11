import { useEffect, useMemo, useState } from "react";
import { useAppState, useActions } from "../../../state/AppContext";
import * as api from "../../../data/client";
import { summarizeModuleAnalytics } from "../../../data/analyticsAdapter";
import { stateMeta } from "../../../utils/bands";
import { formatNumber } from "../../../utils/format";
import { groupOwnerAnalytics, recordOwnerQueryKeys } from "../../../data/ownerAnalytics";
import LoadingState from "../../shared/LoadingState";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

const SUPPORTED_STATES = new Set(["proper", "incomplete", "inaccurate"]);
const RECORD_FILTERS = [
  { id: "proper", label: "Clean" },
  { id: "incomplete", label: "Missing information" },
  { id: "inaccurate", label: "Wrong values" },
  { id: "suspicious", label: "Looks fabricated" },
  { id: "suspected_duplicate", label: "Possible duplicate" },
  { id: "confirmed_duplicate", label: "Certain duplicate" },
];

const SEVERITY_TONE = {
  high: { background: "var(--risk-soft)", color: "var(--risk)" },
  medium: { background: "var(--attention-soft)", color: "var(--attention)" },
  low: { background: "var(--surface-sunken)", color: "var(--muted)" },
};

function filterLabel(stateId) {
  return RECORD_FILTERS.find((state) => state.id === stateId)?.label || stateId;
}

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

function recordIdentity(record) {
  return record.crmRecordId || record.findingId || record.recordRef || null;
}

function matchesActiveState(record, activeState) {
  if (!activeState) return true;
  if (!SUPPORTED_STATES.has(activeState)) return false;
  return record.state === activeState;
}

function issueFields(record) {
  const issues = record.issues ?? [];
  if (issues.length === 0) return null;
  const visible = issues
    .slice(0, 4)
    .map((issue) => issue.fieldLabel || issue.fieldApiName)
    .join(", ");
  const extra = issues.length > 4 ? ` +${issues.length - 4} more` : "";
  return `${visible}${extra}`;
}

function SeverityBadge({ severity }) {
  if (!severity) return null;
  const tone = SEVERITY_TONE[String(severity).toLowerCase()];
  if (!tone) return null;
  return (
    <span
      className="inline-flex shrink-0 px-1.5 py-0.5 text-[10px] font-semibold tracking-wider uppercase"
      style={{ background: tone.background, color: tone.color }}
    >
      {severity}
    </span>
  );
}

function RecordRow({ record }) {
  const identity = recordIdentity(record);
  const title = recordTitle(record);
  const fields = issueFields(record);
  const created = record.createdTime || record.computedAt;
  const createdBy = record.createdBy || record.ownerName;

  return (
    <tr className="hover:bg-surface-sunken/70">
      <td className="min-w-[10rem] border-b border-line py-3 pr-4 align-top">
        <p className="font-semibold tracking-tight text-ink [overflow-wrap:anywhere]">
          {title}
        </p>
        {identity && identity !== title && (
          <p className="mono mt-0.5 text-[11px] text-ink-muted [overflow-wrap:anywhere]">
            {identity}
          </p>
        )}
      </td>
      <td className="min-w-[6rem] border-b border-line px-3 py-3 align-top text-ink-soft">
        {record.module || "—"}
      </td>
      <td className="min-w-[16rem] border-b border-line px-3 py-3 align-top">
        <div className="flex min-w-0 flex-wrap items-start gap-x-2 gap-y-1">
          <SeverityBadge severity={record.severity} />
          <p className="min-w-0 text-[13px] leading-snug text-ink">
            {record.reason || "Quality issue detected"}
          </p>
        </div>
        {fields && (
          <p className="mt-1 text-[12px] leading-snug text-ink-muted">{fields}</p>
        )}
      </td>
      <td className="min-w-[8rem] border-b border-line px-3 py-3 align-top text-ink-soft">
        {createdBy || "—"}
      </td>
      <td className="min-w-[7rem] border-b border-line py-3 pl-3 align-top">
        <span className="mono text-[12px] text-ink-muted">{formatDate(created)}</span>
      </td>
    </tr>
  );
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
  const scopedBreakdown = useMemo(() => {
    if (!scan) return null;
    if (!filterModules.length) return scan.stateBreakdown ?? null;
    const selected = (scan.moduleAnalytics ?? []).filter((module) =>
      filterModules.includes(module.moduleApiName)
    );
    return summarizeModuleAnalytics(selected).stateBreakdown;
  }, [filterModules, scan]);
  const scanCleanCount = Number(scopedBreakdown?.proper);

  function countForState(stateId) {
    if (SUPPORTED_STATES.has(stateId) && listedCounts) {
      return Number(listedCounts[stateId] || 0);
    }
    return Number(scopedBreakdown?.[stateId] || 0);
  }

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
        ? `${formatNumber(scanCleanCount)} clean records were counted; they could not be listed from the stored export.`
        : "Clean records are not listed.";
    }
    if (activeState && !SUPPORTED_STATES.has(activeState)) {
      return "This classification is not stored on the current scan yet.";
    }
    if (activeState) {
      return "No records match the selected state and module filters.";
    }
    if (scanDepth === "quick") {
      return "No matching records. Quick scans skip optional missing fields.";
    }
    return "No matching records.";
  }, [activeState, scanCleanCount, scanDepth]);

  const inScopeCount = activeState
    ? countForState(activeState)
    : Number(listedCounts?.listedRecordCount ?? data?.summary?.storedSampleCount ?? 0);
  const showSampleNote =
    activeState !== "proper" &&
    data?.summary?.measured &&
    Number(data.summary.affectedRecordCount) > Number(data.summary.storedSampleCount || 0);
  const heading = activeState
    ? `${filterLabel(activeState)} · ${formatNumber(inScopeCount)}`
    : `Records · ${formatNumber(inScopeCount)}`;

  return (
    <div className="flex min-w-0 flex-col gap-5 py-4 pb-8 @max-[760px]:py-3 @max-[760px]:pb-6">
      <div
        className="grid min-w-0 grid-cols-2 gap-2 @min-[640px]:grid-cols-3 @min-[1100px]:grid-cols-6"
        role="tablist"
        aria-label="Filter by record state"
      >
        {RECORD_FILTERS.map((state) => {
          const meta = stateMeta(state.id);
          const isActive = activeState === state.id;
          const count =
            scopedBreakdown || listedCounts ? countForState(state.id) : null;
          return (
            <button
              key={state.id}
              type="button"
              role="tab"
              aria-selected={isActive}
              className={cn(
                "m-0 flex min-w-0 cursor-pointer flex-col items-start gap-1 rounded-md border px-3 py-2.5 text-left font-[inherit]",
                isActive
                  ? "border-line bg-surface text-ink"
                  : "border-transparent bg-surface/80 text-ink-muted hover:border-line hover:text-ink-soft"
              )}
              style={
                isActive
                  ? { boxShadow: `inset 0 3px 0 ${meta?.color || "var(--brand)"}` }
                  : undefined
              }
              onClick={() => setFilter({ focusState: isActive ? null : state.id })}
            >
              <span className="flex min-w-0 items-center gap-1.5">
                <span
                  className="size-1.5 shrink-0 rounded-full"
                  style={{ background: meta?.color || "var(--muted)" }}
                  aria-hidden="true"
                />
                <span className="min-w-0 text-[11px] font-semibold leading-tight tracking-wide uppercase">
                  {state.label}
                </span>
              </span>
              <strong
                className="mono text-[20px] font-semibold tracking-tight"
                style={{
                  color: isActive && meta?.color ? meta.color : "var(--ink)",
                }}
              >
                {count === null ? "—" : formatNumber(count)}
              </strong>
            </button>
          );
        })}
      </div>

      <section className="flex min-w-0 flex-col rounded-md border border-line bg-surface p-5 @min-[640px]:p-6">
        <header className="mb-4 flex shrink-0 flex-wrap items-end justify-between gap-3 border-b border-line pb-3">
          <h2 className="font-heading text-xl font-semibold tracking-tight text-ink">
            {heading}
          </h2>
          <form
            className="min-w-0 @max-[760px]:w-full"
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
              className="min-h-[34px] w-[min(280px,100%)] border border-line bg-paper px-2.5 py-1.5 text-[13px] text-ink placeholder:text-ink-muted @max-[760px]:w-full"
            />
          </form>
        </header>

        {showSampleNote && (
          <p className="mb-4 text-[13px] leading-relaxed text-ink-muted">
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
          <p className="max-w-[46ch] text-sm leading-relaxed text-ink-soft">
            Record-level findings were not measured in this scan.
          </p>
        ) : rows.length === 0 ? (
          <div className="py-8">
            <p className="font-heading text-lg font-semibold tracking-tight text-ink">
              No matching records
            </p>
            <p className="mt-1.5 max-w-[46ch] text-sm leading-relaxed text-ink-muted">
              {emptyHint}
            </p>
          </div>
        ) : (
          <>
            <div className="min-w-0 overflow-x-auto overscroll-x-contain">
              <table className="w-full min-w-[52rem] border-collapse text-[13px]">
                <caption className="sr-only">
                  Flagged records, including module, issue, created by, and created date
                </caption>
                <thead>
                  <tr>
                    <th className="min-w-[10rem] border-b border-line py-2.5 pr-4 text-left align-middle">
                      <span className="eyebrow">Record</span>
                    </th>
                    <th className="min-w-[6rem] border-b border-line px-3 py-2.5 text-left align-middle">
                      <span className="eyebrow">Module</span>
                    </th>
                    <th className="min-w-[16rem] border-b border-line px-3 py-2.5 text-left align-middle">
                      <span className="eyebrow">What is wrong with it</span>
                    </th>
                    <th className="min-w-[8rem] border-b border-line px-3 py-2.5 text-left align-middle">
                      <span className="eyebrow">Created by</span>
                    </th>
                    <th className="min-w-[7rem] border-b border-line py-2.5 pl-3 text-left align-middle">
                      <span className="eyebrow">Created</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((record) => (
                    <RecordRow key={record.findingId} record={record} />
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-4 flex items-center justify-between gap-4 @max-[760px]:flex-col @max-[760px]:items-start">
              <span className="text-[13px] text-ink-muted">
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
                <span className="mono text-[13px] text-ink-muted">
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
