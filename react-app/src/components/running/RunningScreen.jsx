import { useEffect, useMemo, useRef, useState } from "react";
import { useAppState, useAppDispatch } from "../../state/AppContext";
import { adaptAnalyticsResults } from "../../data/analyticsAdapter";
import useScanAnalytics from "../../hooks/useScanAnalytics";
import ModuleProgressList from "./ModuleProgressList";
import "./RunningScreen.css";

const STATUS_MESSAGE = {
  CREATED: "Preparing the scan securely.",
  AUTH_VALIDATING: "Confirming access to the connected CRM account.",
  DISCOVERING: "Reviewing the selected modules.",
  PLANNED: "Preparing the selected records for extraction.",
  EXTRACTING: "Reading records from the connected CRM account.",
  PROCESSING: "Checking the extracted records for quality issues.",
  COMPLETED: "Finishing the report.",
  PAUSED_RETRYABLE: "The scan is paused and can be continued safely.",
  FAILED_TERMINAL: "The scan needs attention before it can continue.",
};

const AUTOMATION_MESSAGE = {
  starting: "Starting the automatic scan.",
  running: "Advancing the scan pipeline.",
  completed: "Scan completed.",
  stopped: "Automatic scanning is paused.",
};

export default function RunningScreen() {
  const { connection, scanConfig, scanId, scanContext } = useAppState();
  const dispatch = useAppDispatch();
  const {
    status,
    results,
    loading,
    error,
    refresh,
    advance,
    lastAdvance,
    automationState,
    automationMessage,
  } = useScanAnalytics(scanId);
  const progressHighWater = useRef({ scanId: null, modules: {} });
  const countedAdvance = useRef(null);
  const [liveUsage, setLiveUsage] = useState({ credits: 0, throttleRetries: 0 });

  useEffect(() => {
    countedAdvance.current = null;
    setLiveUsage({ credits: 0, throttleRetries: 0 });
  }, [scanId]);

  useEffect(() => {
    if (!lastAdvance || countedAdvance.current === lastAdvance) return;
    countedAdvance.current = lastAdvance;
    setLiveUsage((current) => ({
      credits:
        current.credits + Math.max(0, Number(lastAdvance.zohoCreditsConsumed) || 0),
      throttleRetries:
        current.throttleRetries + (lastAdvance.pollingDeferred === true ? 1 : 0),
    }));
  }, [lastAdvance]);

  const moduleMetadata = new Map(
    (connection?.accessibleModules ?? []).map((module) => [module.apiName, module])
  );
  const scopedModules = scanConfig.modules.map((apiName) => ({
    apiName,
    label: moduleMetadata.get(apiName)?.label || apiName,
    recordCount: Number(moduleMetadata.get(apiName)?.recordCount) || 0,
  }));
  const progress = useMemo(() => {
    if (progressHighWater.current.scanId !== scanId) {
      progressHighWater.current = { scanId, modules: {} };
    }
    const nextProgress = {};
    for (const module of status?.modules ?? []) {
      const bulkCount = Math.max(
        0,
        ...(module.bulkJobs ?? []).map((job) => Number(job.providerRecordCount) || 0)
      );
      const expectedTotal = Number(module.expectedRecordCount) || bulkCount;
      const scanned = Number(module.recordsProcessed) || 0;
      const taskTypes = new Set(
        (module.tasks ?? [])
          .filter((task) => task.status === "SUCCEEDED")
          .map((task) => task.taskType)
      );
      const bulkStatuses = new Set(
        (module.bulkJobs ?? []).map((job) => String(job.status || ""))
      );
      let percent = 4;
      let phase = "planning";
      if (module.status === "COMPLETED") {
        percent = 100;
        phase = "done";
      } else if (module.status === "PROCESSING" || taskTypes.has("PREPARE_BATCHES")) {
        percent = expectedTotal
          ? 35 + Math.round(Math.min(1, scanned / expectedTotal) * 60)
          : 35;
        phase = "classifying";
      } else if (
        module.status === "PROCESSING_PLANNED" ||
        bulkStatuses.has("PROCESSING_PLANNED") ||
        bulkStatuses.has("DOWNLOADED")
      ) {
        percent = 34;
        phase = "preparing";
      } else if (
        bulkStatuses.has("READY_TO_DOWNLOAD") ||
        bulkStatuses.has("DOWNLOAD_RETRYABLE")
      ) {
        percent = 30;
        phase = "preparing";
      } else if (
        module.status === "EXTRACTING" ||
        bulkStatuses.has("SUBMITTED") ||
        bulkStatuses.has("PROCESSING")
      ) {
        percent = bulkStatuses.has("PROCESSING") ? 24 : 18;
        phase = "extracting";
      } else if (module.status === "PLANNED") {
        percent = 10;
        phase = "planning";
      } else if (module.status === "DISCOVERING") {
        percent = 6;
        phase = "planning";
      }
      const priorPercent = Number(
        progressHighWater.current.modules[module.moduleApiName]
      ) || 0;
      percent = module.status === "COMPLETED" ? 100 : Math.max(priorPercent, percent);
      progressHighWater.current.modules[module.moduleApiName] = percent;
      nextProgress[module.moduleApiName] = {
        scanned,
        estimatedTotal: expectedTotal,
        percent,
        phase,
        indeterminate: false,
      };
    }
    return nextProgress;
  }, [scanId, status]);
  const completedModules = useMemo(
    () =>
      (status?.modules ?? [])
        .filter((module) => module.status === "COMPLETED")
        .map((module) => module.moduleApiName),
    [status]
  );
  const activeModule = useMemo(() => {
    const pendingModules = (status?.modules ?? []).filter(
      (module) => module.status !== "COMPLETED"
    );
    return (
      pendingModules.find((module) => module.status !== "PLANNED")
        ?.moduleApiName ?? pendingModules[0]?.moduleApiName ?? null
    );
  }, [status]);
  const allDone = completedModules.length === scopedModules.length && scopedModules.length > 0;
  const recordsExtracted = useMemo(
    () =>
      (status?.modules ?? []).reduce(
        (total, module) => total + (Number(module.recordsDownloaded) || 0),
        0
      ),
    [status]
  );
  const completedModuleCount = Number(status?.completedModuleCount) || 0;
  const plannedModuleCount =
    Number(status?.plannedModuleCount) || scopedModules.length;
  const friendlyStatusMessage =
    STATUS_MESSAGE[status?.status] ?? "Advancing the scan pipeline.";
  const visibleAutomationMessage = ["waiting-provider", "waiting-worker"].includes(
    automationState
  )
    ? automationMessage
    : AUTOMATION_MESSAGE[automationState] ?? "The scan is progressing.";
  const totalSourceRecords = useMemo(
    () =>
      (results?.modules ?? []).reduce(
        (total, module) => total + (Number(module.sourceRecordCount) || 0),
        0
      ),
    [results]
  );
  const emptyResults =
    Boolean(results?.modules?.length) && totalSourceRecords === 0;

  useEffect(() => {
    if (results && !emptyResults) {
      dispatch({
        type: "scanComplete",
        scan: {
          ...adaptAnalyticsResults(results),
          ...(scanContext ? { reportContext: scanContext } : {}),
        },
      });
    }
  }, [dispatch, emptyResults, results, scanContext]);

  if (emptyResults) {
    const moduleNames = results.modules
      .map((module) => module.moduleApiName)
      .filter(Boolean)
      .join(", ");
    return (
      <div className="running-screen">
        <header className="running-header">
          <p className="eyebrow">Scan complete</p>
          <h1>No records matched this scan</h1>
          <p className="running-subhead">
            Zoho returned no {moduleNames || "CRM"} records for the selected
            date range and activity clock. Nothing failed and no records were changed.
          </p>
        </header>

        <section className="panel running-empty" aria-labelledby="empty-scan-title">
          <h2 id="empty-scan-title">Try a broader scope</h2>
          <p>
            Expand the date range or switch between Created time and Modified
            time, then run the scan again.
          </p>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => dispatch({ type: "reset" })}
          >
            Change scan filters
          </button>
        </section>
      </div>
    );
  }

  return (
    <div className="running-screen">
      <header className="running-header">
        <p className="eyebrow">{allDone ? "Wrapping up" : "Scanning"}</p>
        <h1>{allDone ? "Putting your report together\u2026" : "Reading your records\u2026"}</h1>
        <p className="running-subhead">
          Read-only the whole way through. Nothing in your CRM is being changed.
        </p>
        <div className="running-refresh">
          <div className="running-status-copy">
            <span className="eyebrow">Reading backend status</span>
            <p>{friendlyStatusMessage}</p>
          </div>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={loading}
            onClick={refresh}
          >
            {loading ? "Refreshing…" : "Refresh status"}
          </button>
          {!allDone && (
            <button
              type="button"
              className="btn btn-primary"
              disabled={loading || automationState !== "stopped"}
              onClick={advance}
            >
              {automationState === "stopped"
                ? "Continue scan"
                : "Automatic scan active"}
            </button>
          )}
        </div>
        <p className={`running-operation running-operation-${automationState}`} role="status">
          {visibleAutomationMessage}
        </p>
        {error && <p className="running-error" role="alert">{error}</p>}
      </header>

      <div className="panel">
        <div className="running-stats" aria-label="Live scan progress">
          <div>
            <strong className="mono">{recordsExtracted.toLocaleString("en-IN")}</strong>
            <span>Records extracted</span>
          </div>
          <div>
            <strong className="mono">
              {completedModuleCount}/{plannedModuleCount}
            </strong>
            <span>Modules done</span>
          </div>
          <div>
            <strong className="mono">{liveUsage.credits.toLocaleString("en-IN")}</strong>
            <span>API credits used</span>
          </div>
          <div>
            <strong className="mono">
              {liveUsage.throttleRetries.toLocaleString("en-IN")}
            </strong>
            <span>Throttle retries</span>
          </div>
        </div>
        <ModuleProgressList
          modules={scopedModules}
          progress={progress}
          completed={completedModules}
          activeModule={activeModule}
        />
      </div>
    </div>
  );
}
