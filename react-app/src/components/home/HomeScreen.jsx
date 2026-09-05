import { useEffect, useState } from "react";
import { useAppDispatch, useAppState } from "../../state/AppContext";
import { adaptAnalyticsResults } from "../../data/analyticsAdapter";
import { activateConnection, getScanHistory, getScanResults, ZOHO_CONSENT_URL } from "../../data/client";
import { formatNumber, formatReportPeriod } from "../../utils/format";
import { cn } from "@/lib/utils";
import { ContentContainer, PageHeader } from "../layout";
import { Button } from "@/components/ui/button";
import Band from "../shared/Band";
import Dropdown from "../shared/Dropdown";
import LoadingState from "../shared/LoadingState";

const COMPLETED_BAND = {
  id: "completed",
  label: "Completed",
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

function statusLabel(status) {
  if (!status) return "Unknown";
  if (status === "COMPLETED") return "Completed";
  if (status === "FAILED_TERMINAL") return "Failed";
  return String(status)
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function clockLabel(clock) {
  if (clock === "Modified_Time") return "Modified time";
  if (clock === "Created_Time") return "Created time";
  return clock || null;
}

function depthLabel(depth) {
  const text = String(depth || "").trim();
  if (!text) return null;
  return `${text.charAt(0).toUpperCase()}${text.slice(1)}`;
}

function canOpenScan(scan) {
  return scan.status === "COMPLETED" && scan.hasResults;
}

function canResumeScan(scan) {
  return !["COMPLETED", "FAILED_TERMINAL"].includes(scan.status);
}

function latestHeadline(scan) {
  if (scan.status === "COMPLETED" && scan.hasResults) return "Report ready";
  if (scan.status === "COMPLETED") return "Scan completed";
  if (scan.status === "FAILED_TERMINAL") return "Scan failed";
  return "Scan in progress";
}

function ModuleSummary({ modules }) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? modules : modules.slice(0, 3);
  const remaining = modules.length - visible.length;
  return (
    <div className="max-w-[280px]">
      <span>{visible.join(", ") || "—"}</span>
      {modules.length > 3 && (
        <button
          type="button"
          className="ml-1.5 inline border-0 bg-transparent p-0 font-[inherit] text-brand hover:underline"
          onClick={() => setExpanded((current) => !current)}
        >
          {expanded ? "Show less" : `+ ${remaining} more`}
        </button>
      )}
    </div>
  );
}

function ScanStatus({ status }) {
  if (status === "COMPLETED") return <Band band={COMPLETED_BAND} />;
  const failed = status === "FAILED_TERMINAL";
  return (
    <span
      title={status}
      className={cn(
        "inline-flex items-center rounded-full px-2 py-[3px] text-[11px] font-semibold tracking-wide",
        failed ? "bg-risk-soft text-risk" : "bg-surface-sunken text-ink-soft"
      )}
    >
      {statusLabel(status)}
    </span>
  );
}

function ScanActions({
  scan,
  openingScanId,
  onOpen,
  onResume,
  size = "sm",
  emphasize = false,
}) {
  const canOpen = canOpenScan(scan);
  const canResume = canResumeScan(scan);
  if (!canOpen && !canResume) return null;
  const variant = emphasize ? "default" : "outline";
  return (
    <>
      {canOpen && (
        <Button
          type="button"
          variant={variant}
          size={size}
          disabled={openingScanId === scan.scanId}
          onClick={() => onOpen(scan)}
        >
          {openingScanId === scan.scanId ? "Opening…" : "Open report"}
        </Button>
      )}
      {canResume && (
        <Button
          type="button"
          variant={variant}
          size={size}
          onClick={() => onResume(scan)}
        >
          Resume
        </Button>
      )}
    </>
  );
}

function LatestStat({ label, children, mono = false }) {
  return (
    <div className="min-w-0">
      <dt className="eyebrow">{label}</dt>
      <dd
        className={cn(
          "mt-1.5 text-[15px] font-medium tracking-tight text-ink",
          mono && "mono text-base"
        )}
      >
        {children}
      </dd>
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
      <ContentContainer className="flex min-h-0 w-full flex-1 flex-col py-6">
        <LoadingState label="Restoring your account" />
      </ContentContainer>
    );
  }

  const organizationName = connection?.organizationName || "Zoho CRM";
  const latestScan = connection
    ? scanHistory.find(
        (scan) => scan.connection?.connectionId === connection.connectionId
      ) ?? null
    : null;
  const latestPeriod = latestScan
    ? formatReportPeriod(latestScan.fromUtc, latestScan.toUtc)
    : null;
  const latestClock = latestScan ? clockLabel(latestScan.clock) : null;
  const latestDepth = latestScan ? depthLabel(latestScan.depth) : null;
  const latestActionIsPrimary =
    latestScan && (canOpenScan(latestScan) || canResumeScan(latestScan));

  return (
    <ContentContainer className="pb-12 pt-8 sm:pt-10">
      {connection ? (
        <div className="mb-8 flex min-w-0 flex-wrap items-end justify-end gap-x-3 gap-y-2">
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
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="lg"
              onClick={() => window.location.assign(ZOHO_CONSENT_URL)}
            >
              Connect another Zoho account
            </Button>
            <Button
              type="button"
              variant={latestActionIsPrimary ? "outline" : "default"}
              size="lg"
              onClick={() => dispatch({ type: "showSetup" })}
            >
              New scan
            </Button>
          </div>
        </div>
      ) : (
        <PageHeader
          title="Reports"
          description="Connect Zoho CRM to start measuring data health for this workspace."
          actions={
            <Button
              type="button"
              size="lg"
              onClick={() => dispatch({ type: "showSetup" })}
            >
              Connect Zoho CRM
            </Button>
          }
        />
      )}

      {(connectionNotice || error) && (
        <div className="mb-8 space-y-2">
          {connectionNotice && (
            <p className="text-[13px] text-ink-soft">{connectionNotice}</p>
          )}
          {error && (
            <p className="text-[13px] text-risk" role="alert">
              {error}
            </p>
          )}
        </div>
      )}

      {connection && (
        <section
          className="mb-12 border-b border-line pb-10"
          aria-labelledby="latest-scan-heading"
        >
          <p className="eyebrow">Latest scan</p>
          {latestScan ? (
            <>
              <div className="mt-3 flex flex-wrap items-end justify-between gap-x-8 gap-y-5">
                <div className="min-w-0 max-w-[46rem]">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                    <h2
                      id="latest-scan-heading"
                      className="font-heading text-xl font-semibold tracking-tight text-ink sm:text-2xl"
                    >
                      {latestHeadline(latestScan)}
                    </h2>
                    <ScanStatus status={latestScan.status} />
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-ink-soft">
                    {readableDate(latestScan.completedAt || latestScan.createdAt)}
                    {latestPeriod ? ` · ${latestPeriod}` : ""}
                    {latestClock ? ` · ${latestClock}` : ""}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <ScanActions
                    scan={latestScan}
                    openingScanId={openingScanId}
                    onOpen={openReport}
                    onResume={resumeScan}
                    size="lg"
                    emphasize
                  />
                </div>
              </div>
              <dl className="mt-8 grid max-w-3xl grid-cols-2 gap-x-8 gap-y-5 sm:grid-cols-4">
                <LatestStat label="Records" mono>
                  {formatNumber(latestScan.recordCount)}
                </LatestStat>
                <LatestStat label="Modules">
                  {latestScan.modules?.length
                    ? `${latestScan.modules.length} ${
                        latestScan.modules.length === 1 ? "module" : "modules"
                      }`
                    : "—"}
                </LatestStat>
                <LatestStat label="Depth">{latestDepth || "—"}</LatestStat>
                <LatestStat label="Created">
                  {readableDate(latestScan.createdAt)}
                </LatestStat>
              </dl>
              {latestScan.modules?.length > 0 && (
                <div className="mt-6 max-w-[62ch] text-[13px] leading-relaxed text-ink-muted">
                  <ModuleSummary modules={latestScan.modules} />
                </div>
              )}
            </>
          ) : (
            <div className="mt-3 max-w-[42rem]">
              <h2
                id="latest-scan-heading"
                className="font-heading text-xl font-semibold tracking-tight text-ink sm:text-2xl"
              >
                No scans yet
              </h2>
              <p className="mt-2 text-sm leading-relaxed text-ink-soft">
                Run a scan to measure data health for {organizationName}. Completeness,
                accuracy, and duplicates are scored from the modules this login can
                see.
              </p>
            </div>
          )}
        </section>
      )}

      <section className="min-w-0 rounded-md border border-line bg-surface p-4 sm:p-5">
        <div className="mb-3 flex min-w-0 flex-wrap items-baseline justify-between gap-x-4 gap-y-2">
          <div>
            <p className="eyebrow">History</p>
            <h2 className="mt-0.5 font-heading text-lg font-semibold tracking-tight text-ink">
              Past scans
            </h2>
          </div>
          <div className="flex items-end gap-3">
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
            <span className="mono text-ink-muted">
              {visibleScans.length}
              {historyConnectionId !== "all" ? ` / ${scanHistory.length}` : ""}
            </span>
          </div>
        </div>

        {visibleScans.length === 0 ? (
          <p className="rounded-md border border-dashed border-line px-4 py-8 text-center text-[13px] text-ink-muted">
            {scanHistory.length === 0
              ? "No scans have been created for this user yet."
              : "No scans have been created with this Zoho account."}
          </p>
        ) : (
          <div className="min-w-0 overflow-x-auto overscroll-x-contain">
            <table className="w-full min-w-[720px] border-collapse text-[13px]">
              <thead>
                <tr>
                  {["Zoho account", "Email", "Modules", "Records", "Created", "Status", "Action"].map(
                    (heading) => (
                      <th
                        key={heading}
                        className="px-2.5 py-1.5 text-left text-[11px] font-semibold tracking-wider text-ink-muted uppercase"
                      >
                        {heading}
                      </th>
                    )
                  )}
                </tr>
              </thead>
              <tbody>
                {visibleScans.map((scan) => {
                  const canOpen = scan.status === "COMPLETED" && scan.hasResults;
                  const canResume = !["COMPLETED", "FAILED_TERMINAL"].includes(scan.status);
                  const accountName =
                    scan.connection?.organizationName ||
                    scan.connection?.name ||
                    "Unknown account";
                  const accountEmail = scan.connection?.email || "—";
                  return (
                    <tr
                      key={scan.scanId}
                      className="border-t border-line hover:bg-surface-sunken"
                    >
                      <td className="px-2.5 py-1.5 align-middle">
                        <span className="font-semibold text-ink">{accountName}</span>
                      </td>
                      <td className="px-2.5 py-1.5 align-middle">
                        <span className="text-xs text-ink-muted">{accountEmail}</span>
                      </td>
                      <td className="px-2.5 py-1.5 align-middle">
                        <ModuleSummary modules={scan.modules} />
                      </td>
                      <td className="mono px-2.5 py-1.5 align-middle">
                        {formatNumber(scan.recordCount)}
                      </td>
                      <td className="px-2.5 py-1.5 align-middle whitespace-nowrap text-ink-soft">
                        {readableDate(scan.createdAt)}
                      </td>
                      <td className="px-2.5 py-1.5 align-middle">
                        <ScanStatus status={scan.status} />
                      </td>
                      <td className="px-2.5 py-1.5 text-right align-middle whitespace-nowrap">
                        {canOpen && (
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            disabled={openingScanId === scan.scanId}
                            onClick={() => openReport(scan)}
                          >
                            {openingScanId === scan.scanId ? "Opening…" : "Open report"}
                          </Button>
                        )}
                        {canResume && (
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => resumeScan(scan)}
                          >
                            Resume
                          </Button>
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
