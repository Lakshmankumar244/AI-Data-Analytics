import { useEffect, useMemo, useState } from "react";
import { useAppState } from "../../../state/AppContext";
import * as api from "../../../data/client";
import {
  FIX_PAGE_SIZE,
  ISSUE_TYPE_FILTERS,
  SEVERITY_FILTERS,
  isFixIndexUnavailable,
} from "../../../data/fixRecords";
import { groupOwnerAnalytics } from "../../../data/ownerAnalytics";
import { formatNumber } from "../../../utils/format";
import LoadingState from "../../shared/LoadingState";
import Dropdown from "../../shared/Dropdown";
import { Button } from "@/components/ui/button";
import FixKpis from "./FixKpis";
import FixRecordsTable from "./FixRecordsTable";
import FixExportButton from "./FixExportButton";

function FixEmpty({ title, children, role }) {
  return (
    <div className="flex min-w-0 flex-col py-4 pb-8 @max-[760px]:py-3 @max-[760px]:pb-6">
      <section className="min-w-0 rounded-md border border-line bg-surface p-5 @min-[640px]:p-6">
        <h2 className="font-heading text-xl font-semibold tracking-tight text-ink">
          {title}
        </h2>
        <p className="mt-2 mb-0 max-w-[46ch] text-sm leading-relaxed text-ink-soft" role={role}>
          {children}
        </p>
      </section>
    </div>
  );
}

function defaultModule(scan) {
  return String(scan?.moduleFindings?.[0]?.apiName || "").trim();
}

export default function FixTab() {
  const { scanId, scan } = useAppState();
  const scannedModules = scan?.moduleFindings ?? [];
  const owners = useMemo(
    () => groupOwnerAnalytics(scan?.moduleAnalytics ?? [], []),
    [scan]
  );
  const [module, setModule] = useState(() => defaultModule(scan));
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [owner, setOwner] = useState("");
  const [severity, setSeverity] = useState("");
  const [issueType, setIssueType] = useState("");
  const [cursor, setCursor] = useState(null);
  const [cursorStack, setCursorStack] = useState([]);
  const [data, setData] = useState(null);
  const [tableLoading, setTableLoading] = useState(true);
  const [error, setError] = useState(null);
  const [indexUnavailable, setIndexUnavailable] = useState(false);

  const filterKey = `${module}|${submittedQuery}|${owner}|${severity}|${issueType}`;
  const [activeKey, setActiveKey] = useState(filterKey);

  useEffect(() => {
    setModule((current) => current || defaultModule(scan));
  }, [scan]);

  useEffect(() => {
    setModule(defaultModule(scan));
    setQuery("");
    setSubmittedQuery("");
    setOwner("");
    setSeverity("");
    setIssueType("");
    setCursor(null);
    setCursorStack([]);
    setData(null);
  }, [scanId]);

  useEffect(() => {
    const timer = window.setTimeout(() => setSubmittedQuery(query.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    if (filterKey === activeKey) return;
    setActiveKey(filterKey);
    setCursor(null);
    setCursorStack([]);
  }, [activeKey, filterKey]);

  useEffect(() => {
    if (!module) {
      setTableLoading(false);
      return undefined;
    }
    let cancelled = false;
    setTableLoading(true);
    setError(null);
    setIndexUnavailable(false);
    const cursorForRequest = filterKey === activeKey ? cursor : null;
    api
      .getFixRecords(scanId, {
        module,
        cursor: cursorForRequest,
        pageSize: FIX_PAGE_SIZE,
        q: submittedQuery,
        owners: owner ? [owner] : [],
        severity,
        issueType,
      })
      .then((payload) => {
        if (cancelled) return;
        setData(payload);
        setTableLoading(false);
      })
      .catch((requestError) => {
        if (cancelled) return;
        if (isFixIndexUnavailable(requestError)) {
          setIndexUnavailable(true);
          setData(null);
        } else {
          setError(requestError.message);
        }
        setTableLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [
    scanId,
    module,
    submittedQuery,
    owner,
    severity,
    issueType,
    cursor,
    filterKey,
    activeKey,
  ]);

  const moduleOptions = scannedModules.map((item) => ({
    id: item.apiName,
    label: item.label || item.apiName,
  }));
  const ownerOptions = [
    { id: "", label: "All owners" },
    ...owners.map((item) => ({ id: item.ownerKey, label: item.ownerName })),
    { id: "__unassigned__", label: "Unassigned" },
  ];

  if (indexUnavailable) {
    return (
      <FixEmpty title="Re-run scan to use Fix" role="status">
        This scan was finished before the Fix index was available. Run a new scan
        to review defective records here.
      </FixEmpty>
    );
  }

  if (!moduleOptions.length) {
    return (
      <FixEmpty title="Fix is not available">
        No scanned modules were found for this report.
      </FixEmpty>
    );
  }

  const rows = data?.rows ?? [];
  const columns = data?.columns ?? [];
  const affected = Number(data?.kpis?.affectedRecordCount) || 0;

  function goNext() {
    if (!data?.nextCursor) return;
    setCursorStack((stack) => [...stack, cursor]);
    setCursor(data.nextCursor);
  }

  function goPrevious() {
    const previous = cursorStack[cursorStack.length - 1] ?? null;
    setCursorStack((stack) => stack.slice(0, -1));
    setCursor(previous);
  }

  return (
    <div className="flex min-w-0 flex-col gap-5 py-4 pb-8 @max-[760px]:py-3 @max-[760px]:pb-6">
      <header className="flex min-w-0 flex-wrap items-end justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-end gap-2">
          <Dropdown
            label="Module"
            value={module}
            options={moduleOptions}
            onChange={setModule}
          />
          <Dropdown
            label="Owner"
            value={owner}
            options={ownerOptions}
            onChange={setOwner}
          />
          <Dropdown
            label="Severity"
            value={severity}
            options={SEVERITY_FILTERS}
            onChange={setSeverity}
          />
          <Dropdown
            label="Issue type"
            value={issueType}
            options={ISSUE_TYPE_FILTERS}
            onChange={setIssueType}
          />
        </div>
        <div className="ml-auto flex shrink-0 items-end justify-end">
          <FixExportButton
            scanId={scanId}
            disabled={!module || indexUnavailable}
            filters={{
              module,
              q: submittedQuery,
              owners: owner ? [owner] : [],
              severity,
              issueType,
            }}
          />
        </div>
      </header>

      {data ? <FixKpis kpis={data.kpis} /> : null}

      <section className="flex min-w-0 flex-col rounded-md border border-line bg-surface p-5 @min-[640px]:p-6">
        <div className="mb-4 flex min-w-0 flex-wrap items-center justify-between gap-3">
          <h2 className="font-heading text-xl font-semibold tracking-tight text-ink">
            Fix · {formatNumber(affected)}
          </h2>
          <form
            className="ml-auto min-w-0 @max-[760px]:w-full"
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
        </div>

        {error ? (
          <p className="text-[13px] leading-normal text-risk" role="alert">
            {error}
          </p>
        ) : tableLoading || !data ? (
          <LoadingState label="Loading records" />
        ) : rows.length === 0 ? (
          <div className="py-8">
            <p className="font-heading text-lg font-semibold tracking-tight text-ink">
              No matching records
            </p>
            <p className="mt-1.5 max-w-[46ch] text-sm leading-relaxed text-ink-muted">
              No defective records match the selected filters.
            </p>
          </div>
        ) : (
          <>
            <FixRecordsTable columns={columns} rows={rows} />
            <footer className="mt-4 flex flex-wrap items-center justify-end gap-3 @max-[760px]:flex-col @max-[760px]:items-stretch">
              <span className="mr-auto text-[13px] text-ink-muted @max-[760px]:mr-0">
                {formatNumber(rows.length)} record{rows.length === 1 ? "" : "s"} on this page
              </span>
              <div className="flex items-center justify-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={cursorStack.length === 0 && !cursor}
                  onClick={goPrevious}
                >
                  Previous
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={!data.hasMore || rows.length === 0}
                  onClick={goNext}
                >
                  Next
                </Button>
              </div>
            </footer>
          </>
        )}
      </section>
    </div>
  );
}
