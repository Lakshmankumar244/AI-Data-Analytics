import { useEffect, useState } from "react";
import { useAppDispatch, useAppState } from "../../state/AppContext";
import { adaptAnalyticsResults } from "../../data/analyticsAdapter";
import { activateConnection, deleteScan, getScanHistory, getScanResults, ZOHO_CONSENT_URL } from "../../data/client";
import { Trash2 } from "lucide-react";
import { formatNumber, formatReportPeriod, formatScanTimestamp } from "../../utils/format";
import { cn } from "@/lib/utils";
import { ContentContainer, PageHeader } from "../layout";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Toast } from "@/components/ui/toast";
import Band from "../shared/Band";
import Dropdown from "../shared/Dropdown";
import LoadingState from "../shared/LoadingState";

const COMPLETED_BAND = {
  id: "completed",
  label: "Completed",
  color: "var(--strong)",
  soft: "var(--strong-soft)",
};

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
  deletingScanId,
  onOpen,
  onResume,
  onDelete,
  size = "sm",
  emphasize = false,
}) {
  const canOpen = canOpenScan(scan);
  const canResume = canResumeScan(scan);
  const variant = emphasize ? "default" : "outline";
  const busy = openingScanId === scan.scanId || deletingScanId === scan.scanId;
  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      {canOpen && (
        <Button
          type="button"
          variant={variant}
          size={size}
          disabled={busy}
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
          disabled={busy}
          onClick={() => onResume(scan)}
        >
          Resume
        </Button>
      )}
      {onDelete && (
        <Button
          type="button"
          variant="outline"
          size={size}
          disabled={busy}
          onClick={() => onDelete(scan)}
        >
          Delete
        </Button>
      )}
    </div>
  );
}

export default function HomeScreen() {
  const { connection, scanHistory, connectionNotice, historyNeedsRefresh } = useAppState();
  const dispatch = useAppDispatch();
  const [openingScanId, setOpeningScanId] = useState(null);
  const [scanToDelete, setScanToDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(null);
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

  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(() => setToast(null), 2000);
    return () => window.clearTimeout(timer);
  }, [toast]);

  async function openReport(scan) {
    if (scan.status !== "COMPLETED" || !scan.hasResults) return;
    if (!scanHistory.some((item) => item.scanId === scan.scanId)) return;
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
    if (!scanHistory.some((item) => item.scanId === scan.scanId)) return;
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

  function requestDelete(scan) {
    if (deleting) return;
    setError(null);
    setScanToDelete(scan);
  }

  async function confirmDelete() {
    if (!scanToDelete?.scanId || deleting) return;
    setDeleting(true);
    setError(null);
    try {
      await deleteScan(scanToDelete.scanId);
      const deletedScanId = scanToDelete.scanId;
      dispatch({ type: "scanDeleted", scanId: deletedScanId });
      setScanToDelete(null);
      setOpeningScanId((current) => (current === deletedScanId ? null : current));
      setToast({
        id: Date.now(),
        message: "The scan report was deleted.",
      });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "The scan report could not be deleted"
      );
    } finally {
      setDeleting(false);
    }
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
  const latestActionIsPrimary =
    latestScan && (canOpenScan(latestScan) || canResumeScan(latestScan));

  return (
    <>
    <ContentContainer className="pb-10 pt-6 @min-[640px]:pt-8">
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
          className="mb-10 border-b border-line pb-8"
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
                    {formatScanTimestamp(latestScan.createdAt)}
                    {latestPeriod ? ` · ${latestPeriod}` : ""}
                    {latestClock ? ` · ${latestClock}` : ""}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <ScanActions
                    scan={latestScan}
                    openingScanId={openingScanId}
                    deletingScanId={deleting ? scanToDelete?.scanId : null}
                    onOpen={openReport}
                    onResume={resumeScan}
                    onDelete={requestDelete}
                    size="lg"
                    emphasize
                  />
                </div>
              </div>
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
                Run a scan to measure data health for {organizationName}.
              </p>
            </div>
          )}
        </section>
      )}

      <section className="min-w-0 rounded-md border border-line bg-surface p-4 sm:p-5">
        <div className="mb-3 flex min-w-0 flex-wrap items-baseline justify-between gap-x-4 gap-y-2">
          <div>
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
              ? "No scans yet."
              : "No scans for this Zoho account."}
          </p>
        ) : (
          <div className="min-w-0 overflow-x-auto overscroll-x-contain">
            <table className="w-full min-w-[752px] border-collapse text-[13px]">
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
                  <th className="w-9 px-1 py-1.5 text-center">
                    <span className="sr-only">Delete</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {visibleScans.map((scan) => {
                  const accountName =
                    scan.connection?.organizationName ||
                    scan.connection?.name ||
                    "Unknown account";
                  const accountEmail = scan.connection?.email || "—";
                  const isDeletingRow =
                    deleting && scanToDelete?.scanId === scan.scanId;
                  return (
                    <tr
                      key={scan.scanId}
                      className="group/scan border-t border-line hover:bg-surface-sunken"
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
                        {formatScanTimestamp(scan.createdAt)}
                      </td>
                      <td className="px-2.5 py-1.5 align-middle">
                        <ScanStatus status={scan.status} />
                      </td>
                      <td className="px-2.5 py-1.5 text-right align-middle whitespace-nowrap">
                        <ScanActions
                          scan={scan}
                          openingScanId={openingScanId}
                          deletingScanId={deleting ? scanToDelete?.scanId : null}
                          onOpen={openReport}
                          onResume={resumeScan}
                        />
                      </td>
                      <td className="w-9 px-1 py-1.5 text-center align-middle">
                        <button
                          type="button"
                          aria-label="Delete report"
                          disabled={isDeletingRow}
                          onClick={() => requestDelete(scan)}
                          className={cn(
                            "group/delete relative inline-flex size-7 items-center justify-center rounded-md text-risk opacity-0 transition-opacity hover:bg-risk-soft focus-visible:opacity-100 group-hover/scan:opacity-100",
                            "pointer-events-none group-hover/scan:pointer-events-auto focus-visible:pointer-events-auto",
                            isDeletingRow && "pointer-events-auto opacity-100"
                          )}
                        >
                          <Trash2 className="size-3.5" aria-hidden="true" />
                          <span
                            role="tooltip"
                            className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1.5 -translate-x-1/2 rounded-md bg-ink px-2 py-1 text-[11px] font-medium whitespace-nowrap text-on-brand opacity-0 shadow-sm transition-opacity group-hover/delete:opacity-100 group-focus-visible/delete:opacity-100"
                          >
                            Delete report
                          </span>
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <AlertDialog
        open={Boolean(scanToDelete)}
        onOpenChange={(open) => {
          if (deleting) return;
          if (!open) setScanToDelete(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete scan report?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently deletes the report and stored results for this
              scan. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel asChild>
              <Button type="button" variant="outline" disabled={deleting}>
                Cancel
              </Button>
            </AlertDialogCancel>
            <Button
              type="button"
              variant="destructive"
              disabled={deleting}
              onClick={confirmDelete}
            >
              {deleting ? "Deleting…" : "Delete report"}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </ContentContainer>
    <Toast open={Boolean(toast)}>{toast?.message}</Toast>
    </>
  );
}
