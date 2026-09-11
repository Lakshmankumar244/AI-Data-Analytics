import { useCallback, useEffect, useRef, useState } from "react";
import { getScanResults, getScanStatus } from "../data/client";

const STATUS_POLL_MS = 2_000;

function isTerminal(status) {
  return status === "COMPLETED" || status === "FAILED_TERMINAL";
}

export default function useScanAnalytics(scanId) {
  const [status, setStatus] = useState(null);
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(Boolean(scanId));
  const [error, setError] = useState(null);
  const refreshRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    let timer = null;
    let inFlight = false;

    setStatus(null);
    setResults(null);
    setError(null);
    setLoading(Boolean(scanId));

    function clearTimer() {
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
    }

    async function readOnce({ manual = false } = {}) {
      if (!scanId || inFlight) return null;
      inFlight = true;
      if (manual && !cancelled) setLoading(true);
      try {
        const nextStatus = await getScanStatus(scanId);
        if (cancelled) return nextStatus;
        setStatus(nextStatus);
        if (nextStatus.status === "COMPLETED") {
          const nextResults = await getScanResults(scanId);
          if (!cancelled) setResults(nextResults);
        }
        if (!cancelled) setError(null);
        return nextStatus;
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Could not read scan status"
          );
        }
        return null;
      } finally {
        inFlight = false;
        if (!cancelled) setLoading(false);
      }
    }

    function schedule(nextStatus) {
      if (cancelled || !scanId || isTerminal(nextStatus?.status)) return;
      clearTimer();
      timer = setTimeout(() => {
        tick();
      }, STATUS_POLL_MS);
    }

    async function tick() {
      const nextStatus = await readOnce();
      schedule(nextStatus);
    }

    refreshRef.current = async () => {
      clearTimer();
      const nextStatus = await readOnce({ manual: true });
      schedule(nextStatus);
    };

    if (scanId) {
      tick();
    } else {
      setLoading(false);
    }

    return () => {
      cancelled = true;
      clearTimer();
      refreshRef.current = null;
    };
  }, [scanId]);

  const refresh = useCallback(() => refreshRef.current?.(), []);

  return {
    status,
    results,
    loading,
    error,
    refresh,
    lastAdvance: null,
  };
}
