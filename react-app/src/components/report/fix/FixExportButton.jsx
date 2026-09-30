import { useEffect, useState } from "react";
import * as api from "../../../data/client";
import { Button } from "@/components/ui/button";

const POLL_MS = 1500;
const TERMINAL_FAILURE = new Set(["PAUSED_RETRYABLE", "OUTCOME_UNKNOWN"]);

export default function FixExportButton({ scanId, filters, disabled }) {
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [exportId, setExportId] = useState("");

  useEffect(() => {
    if (!busy || !scanId || !exportId) return undefined;
    let cancelled = false;
    let timer = 0;

    async function poll() {
      try {
        const current = await api.getFixExport(scanId, exportId);
        if (cancelled) return;
        const taskStatus = String(current.taskStatus || "");
        if (current.ready || taskStatus === "SUCCEEDED") {
          setStatus("Downloading workbook");
          await api.downloadFixExportFile(scanId, exportId);
          if (cancelled) return;
          setBusy(false);
          setStatus("");
          setExportId("");
          return;
        }
        if (TERMINAL_FAILURE.has(taskStatus)) {
          setBusy(false);
          setStatus("");
          setExportId("");
          setError("Fix export failed. Try again.");
          return;
        }
        setStatus("Preparing workbook");
        timer = window.setTimeout(poll, POLL_MS);
      } catch (failure) {
        if (cancelled) return;
        setBusy(false);
        setStatus("");
        setExportId("");
        setError(failure?.message || "Fix export failed. Try again.");
      }
    }

    poll();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [busy, scanId, exportId]);

  async function startExport() {
    if (busy || disabled || !scanId) return;
    setError("");
    setBusy(true);
    setStatus("Queuing export");
    try {
      const started = await api.startFixExport(scanId, filters);
      const nextId = String(started.exportId || "");
      if (!nextId) {
        throw new Error("Fix export could not be queued");
      }
      if (started.alreadyExported || started.taskStatus === "SUCCEEDED") {
        setStatus("Downloading workbook");
        await api.downloadFixExportFile(scanId, nextId);
        setBusy(false);
        setStatus("");
        setExportId("");
        return;
      }
      setExportId(nextId);
      setStatus("Preparing workbook");
    } catch (failure) {
      setBusy(false);
      setStatus("");
      setExportId("");
      setError(failure?.message || "Fix export could not be queued");
    }
  }

  return (
    <div className="flex min-w-0 flex-col items-end gap-1">
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={Boolean(disabled) || busy || !scanId}
        onClick={startExport}
      >
        {busy ? "Exporting…" : "Export XLSX"}
      </Button>
      {status ? (
        <p className="text-[12px] text-ink-muted">{status}</p>
      ) : null}
      {error ? (
        <p className="text-[12px] text-risk" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
