import { useCallback, useEffect, useRef, useState } from "react";
import { advanceScan, getScanResults, getScanStatus } from "../data/client";

const LOCAL_STEP_DELAY_MS = 750;
const WORKER_CHECK_DELAY_MS = 10_000;
const PROVIDER_INITIAL_DELAY_MS = 15_000;
const PROVIDER_MAX_DELAY_MS = 120_000;

const UNSAFE_BULK_STATES = new Set([
  "SUBMITTING",
  "SUBMISSION_UNKNOWN",
  "DOWNLOADING",
  "DOWNLOAD_UNKNOWN",
  "FAILED_TERMINAL",
  "PAUSED_RETRYABLE",
  "DOWNLOAD_RETRYABLE",
]);

function failureGuidance(error) {
  const code = error?.code || error?.body?.error?.code;
  const nextAction = error?.body?.nextAction;

  if (code === "WORKER_ENQUEUE_OUTCOME_UNKNOWN" || nextAction === "REVIEW_WORKER_JOB") {
    return "Automation stopped. Inspect the Catalyst Job Pool before using Continue scan.";
  }
  if (code === "WORKER_ENQUEUE_REJECTED") {
    return "Automation stopped. Verify the worker function and Job Pool configuration, then use Continue scan.";
  }
  if (nextAction === "REVIEW_BULK_JOB") {
    return "Automation stopped because the Bulk Read job needs review. Check its stored status before continuing.";
  }
  if (error?.status === 401 || error?.status === 403) {
    return "Automation stopped because the Zoho connection is no longer authorized. Reconnect before continuing.";
  }
  return "Automation stopped safely. Review the backend message, then use Refresh status or Continue scan.";
}

function unsafeStatusMessage(scanStatus) {
  if (scanStatus?.status === "FAILED_TERMINAL") {
    return "The scan reached a terminal failure. Review the function logs before retrying.";
  }
  const unsafeJob = (scanStatus?.modules ?? [])
    .flatMap((module) => module.bulkJobs ?? [])
    .find((job) => UNSAFE_BULK_STATES.has(job.status));
  if (unsafeJob) {
    return `Automation stopped at Bulk Read state ${unsafeJob.status}. Review that job before continuing.`;
  }
  return null;
}

export default function useScanAnalytics(scanId) {
  const [status, setStatus] = useState(null);
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lastAdvance, setLastAdvance] = useState(null);
  const [automationState, setAutomationState] = useState("starting");
  const [automationMessage, setAutomationMessage] = useState(
    "Starting the scan pipeline…"
  );

  const timerRef = useRef(null);
  const requestActiveRef = useRef(false);
  const automaticRef = useRef(true);
  const mountedRef = useRef(false);
  const advanceRef = useRef(null);
  const providerAttemptRef = useRef(0);

  const clearScheduledStep = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const readStatusAndResults = useCallback(async () => {
    if (!scanId) return null;
    const nextStatus = await getScanStatus(scanId);
    if (!mountedRef.current) return nextStatus;
    setStatus(nextStatus);
    if (nextStatus.status === "COMPLETED") {
      const nextResults = await getScanResults(scanId);
      if (mountedRef.current) setResults(nextResults);
    }
    return nextStatus;
  }, [scanId]);

  const stopAutomation = useCallback(
    (message, nextState = "stopped") => {
      automaticRef.current = false;
      clearScheduledStep();
      if (!mountedRef.current) return;
      setAutomationState(nextState);
      setAutomationMessage(message);
    },
    [clearScheduledStep]
  );

  const scheduleNext = useCallback(
    (outcome) => {
      if (!automaticRef.current || !mountedRef.current) return;

      const nextAction = outcome?.nextAction;
      if (!nextAction || nextAction === "COMPLETE") {
        stopAutomation("Scan completed.", "completed");
        return;
      }

      let delay = LOCAL_STEP_DELAY_MS;
      let stateLabel = "running";
      let message = `Continuing with ${nextAction}…`;
      const waitingForWorker =
        nextAction === "WAIT_FOR_WORKER" ||
        ["QUEUED", "RUNNING"].includes(outcome?.taskStatus);
      const waitingForProvider =
        nextAction === "CHECK_BULK_STATUS" && !waitingForWorker;

      if (waitingForProvider) {
        const backoffDelay = Math.min(
          PROVIDER_INITIAL_DELAY_MS * 2 ** providerAttemptRef.current,
          PROVIDER_MAX_DELAY_MS
        );
        const serverDelay = outcome?.retryAfterSeconds
          ? (Number(outcome.retryAfterSeconds) + 1) * 1_000
          : 0;
        delay = Math.max(backoffDelay, serverDelay);
        providerAttemptRef.current += 1;
        stateLabel = "waiting-provider";
        message = `Zoho is preparing the export. Checking again in ${Math.round(
          delay / 1000
        )} seconds.`;
      } else if (waitingForWorker || outcome?.waitingForProvider) {
        providerAttemptRef.current = 0;
        delay = WORKER_CHECK_DELAY_MS;
        stateLabel = "waiting-worker";
        message = "The Catalyst worker is running. Checking again in 10 seconds.";
      } else {
        providerAttemptRef.current = 0;
      }

      setAutomationState(stateLabel);
      setAutomationMessage(message);
      clearScheduledStep();
      timerRef.current = setTimeout(() => {
        if (advanceRef.current) advanceRef.current(false);
      }, delay);
    },
    [clearScheduledStep, stopAutomation]
  );

  const performAdvance = useCallback(
    async (manual = false) => {
      if (!scanId) return;
      if (requestActiveRef.current) {
        if (!manual && automaticRef.current) {
          clearScheduledStep();
          timerRef.current = setTimeout(() => {
            if (advanceRef.current) advanceRef.current(false);
          }, 1_000);
        }
        return;
      }
      if (manual) {
        automaticRef.current = true;
        providerAttemptRef.current = 0;
      } else if (!automaticRef.current) {
        return;
      }

      clearScheduledStep();
      requestActiveRef.current = true;
      if (mountedRef.current) {
        setLoading(true);
        setError(null);
        setAutomationState("running");
        setAutomationMessage("Advancing the scan pipeline…");
      }

      try {
        const outcome = await advanceScan(scanId);
        if (mountedRef.current) setLastAdvance(outcome);
        const nextStatus = await readStatusAndResults();
        if (!mountedRef.current) return;

        if (nextStatus?.status === "COMPLETED") {
          stopAutomation("Scan completed.", "completed");
          return;
        }
        const unsafeMessage = unsafeStatusMessage(nextStatus);
        if (unsafeMessage) {
          setError(unsafeMessage);
          stopAutomation(unsafeMessage);
          return;
        }
        scheduleNext(outcome);
      } catch (err) {
        if (!mountedRef.current) return;
        const backendMessage =
          err instanceof Error ? err.message : "Could not advance the scan";
        const guidance = failureGuidance(err);
        setError(`${backendMessage} ${guidance}`);
        stopAutomation(guidance);
      } finally {
        requestActiveRef.current = false;
        if (mountedRef.current) setLoading(false);
      }
    },
    [
      clearScheduledStep,
      readStatusAndResults,
      scanId,
      scheduleNext,
      stopAutomation,
    ]
  );

  useEffect(() => {
    advanceRef.current = performAdvance;
  }, [performAdvance]);

  const refresh = useCallback(async () => {
    if (!scanId || requestActiveRef.current) return;
    requestActiveRef.current = true;
    setLoading(true);
    try {
      const nextStatus = await readStatusAndResults();
      const unsafeMessage = unsafeStatusMessage(nextStatus);
      if (unsafeMessage) {
        setError(unsafeMessage);
        stopAutomation(unsafeMessage);
      } else if (nextStatus?.status === "COMPLETED") {
        setError(null);
        stopAutomation("Scan completed.", "completed");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not read scan status");
    } finally {
      requestActiveRef.current = false;
      if (mountedRef.current) setLoading(false);
    }
  }, [readStatusAndResults, scanId, stopAutomation]);

  const advance = useCallback(() => performAdvance(true), [performAdvance]);

  useEffect(() => {
    mountedRef.current = true;
    automaticRef.current = true;
    providerAttemptRef.current = 0;
    setStatus(null);
    setResults(null);
    setError(null);
    setLastAdvance(null);
    setAutomationState("starting");
    setAutomationMessage("Starting the scan pipeline…");

    // This delay also prevents React Strict Mode's development remount from
    // starting the same durable action twice.
    timerRef.current = setTimeout(() => {
      if (advanceRef.current) advanceRef.current(false);
    }, LOCAL_STEP_DELAY_MS);

    return () => {
      mountedRef.current = false;
      automaticRef.current = false;
      clearScheduledStep();
    };
  }, [clearScheduledStep, scanId]);

  return {
    status,
    results,
    loading,
    error,
    refresh,
    advance,
    lastAdvance,
    automationState,
    automationMessage,
  };
}
