import { useEffect, useMemo, useRef, useState } from "react";
import { useAppState, useAppDispatch } from "../../state/AppContext";
import { adaptAnalyticsResults } from "../../data/analyticsAdapter";
import useScanAnalytics from "../../hooks/useScanAnalytics";
import { cn } from "@/lib/utils";
import { ContentContainer } from "../layout";
import { Button } from "@/components/ui/button";
import ModuleProgressList from "./ModuleProgressList";

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

function asCount(value) {
  const count = Number(value);
  return Number.isFinite(count) && count > 0 ? count : 0;
}

function moduleExtractedCount(module) {
  const fromJobs = (module?.bulkJobs ?? []).reduce(
    (highest, job) => Math.max(highest, asCount(job.providerRecordCount)),
    0
  );
  return Math.max(
    asCount(module?.recordsDownloaded),
    asCount(module?.recordsProcessed),
    asCount(module?.expectedRecordCount),
    fromJobs
  );
}

function LiveStat({ label, children }) {
  return (
    <div className="min-w-0">
      <p className="mono text-2xl font-semibold tracking-tight text-ink">{children}</p>
      <p className="mt-1 text-xs text-ink-muted">{label}</p>
    </div>
  );
}

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
  const extractedHighWater = useRef({ scanId: null, total: 0 });
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
  const plannedModuleCount = Math.max(
    asCount(status?.plannedModuleCount),
    scopedModules.length,
    status?.modules?.length || 0
  );
  const completedModuleCount = completedModules.length;
  const activeModule = useMemo(() => {
    const pendingModules = (status?.modules ?? []).filter(
      (module) => module.status !== "COMPLETED"
    );
    return (
      pendingModules.find((module) => module.status !== "PLANNED")
        ?.moduleApiName ?? pendingModules[0]?.moduleApiName ?? null
    );
  }, [status]);
  const allDone = plannedModuleCount > 0 && completedModuleCount === plannedModuleCount;
  const recordsExtracted = useMemo(() => {
    if (extractedHighWater.current.scanId !== scanId) {
      extractedHighWater.current = { scanId, total: 0 };
    }
    const fromStatus = (status?.modules ?? []).reduce(
      (total, module) => total + moduleExtractedCount(module),
      0
    );
    const fromResults = (results?.modules ?? []).reduce(
      (total, module) => total + asCount(module.sourceRecordCount),
      0
    );
    const nextTotal = Math.max(fromStatus, fromResults, extractedHighWater.current.total);
    extractedHighWater.current.total = nextTotal;
    return nextTotal;
  }, [results, scanId, status]);
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
  const isLive =
    !allDone && automationState !== "stopped" && automationState !== "completed";
  const overallPercent = plannedModuleCount
    ? Math.round((completedModuleCount / plannedModuleCount) * 100)
    : 0;

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
      <ContentContainer className="flex min-h-full flex-col justify-center py-12 sm:py-16">
        <div className="max-w-[36rem]" aria-labelledby="empty-scan-title">
          <p className="eyebrow">Scan complete</p>
          <h1 className="mt-3 font-heading text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
            No records matched this scan
          </h1>
          <p className="mt-4 max-w-[34rem] text-sm leading-relaxed text-ink-soft">
            {`Zoho returned no ${moduleNames || "CRM"} records for the selected date range and activity clock. Nothing failed and no records were changed.`}
          </p>
          <h2
            id="empty-scan-title"
            className="mt-8 font-heading text-lg font-semibold tracking-tight text-ink"
          >
            Try a broader scope
          </h2>
          <p className="mt-1.5 max-w-[34rem] text-sm leading-relaxed text-ink-soft">
            Expand the date range or switch between Created time and Modified
            time, then run the scan again.
          </p>
          <Button
            type="button"
            size="lg"
            className="mt-8 min-w-[12rem]"
            onClick={() => dispatch({ type: "reset" })}
          >
            Change scan filters
          </Button>
        </div>
      </ContentContainer>
    );
  }

  return (
    <ContentContainer className="flex min-h-full min-w-0 flex-col pt-8 pb-10 sm:pt-10">
      <div className="flex min-w-0 flex-col gap-8 sm:flex-row sm:items-end sm:justify-between sm:gap-10">
        <div className="min-w-0 max-w-[40rem]">
          <p className="eyebrow flex items-center gap-2">
            {isLive && (
              <span
                className="size-1.5 shrink-0 rounded-full bg-brand motion-safe:animate-pulse"
                aria-hidden="true"
              />
            )}
            {allDone ? "Wrapping up" : "Scanning"}
          </p>
          <h1 className="mt-2 font-heading text-2xl font-semibold tracking-tight text-ink sm:text-3xl">
            {allDone ? "Putting your report together\u2026" : "Reading your records\u2026"}
          </h1>
          <p className="mt-2 max-w-[42ch] text-sm leading-relaxed text-ink-soft">
            Read-only the whole way through. Nothing in your CRM is being changed.
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="lg"
            disabled={loading}
            onClick={refresh}
          >
            {loading ? "Refreshing…" : "Refresh status"}
          </Button>
          {!allDone && (
            <Button
              type="button"
              size="lg"
              disabled={loading || automationState !== "stopped"}
              onClick={advance}
            >
              {automationState === "stopped"
                ? "Continue scan"
                : "Automatic scan active"}
            </Button>
          )}
        </div>
      </div>

      <p
        className={cn(
          "mt-4 text-[13px]",
          automationState === "stopped" && "text-risk",
          automationState === "completed" && "text-strong",
          automationState !== "stopped" &&
            automationState !== "completed" &&
            "text-ink-soft"
        )}
        role="status"
      >
        {visibleAutomationMessage}
      </p>
      <p className="mt-1 text-[13px] text-ink-soft">{friendlyStatusMessage}</p>
      {error && (
        <p className="mt-2 text-[13px] text-risk" role="alert">
          {error}
        </p>
      )}

      <div
        className="mt-10 grid grid-cols-2 gap-x-6 gap-y-5 border-y border-line py-6 sm:grid-cols-4"
        aria-label="Live scan progress"
      >
        <LiveStat label="Records extracted">
          {recordsExtracted.toLocaleString("en-IN")}
        </LiveStat>
        <LiveStat label="Modules done">
          {completedModuleCount}/{plannedModuleCount}
        </LiveStat>
        <LiveStat label="API credits used">
          {liveUsage.credits.toLocaleString("en-IN")}
        </LiveStat>
        <LiveStat label="Throttle retries">
          {liveUsage.throttleRetries.toLocaleString("en-IN")}
        </LiveStat>
      </div>

      <div className="mt-10 min-w-0">
        <div className="mb-6 flex items-baseline justify-between gap-4">
          <p className="eyebrow">Modules</p>
          <p className="mono text-xs text-ink-muted">{overallPercent}%</p>
        </div>
        <div className="mb-8 h-0.5 overflow-hidden bg-surface-sunken">
          <div
            className={cn(
              "h-full bg-brand transition-[width] duration-300 ease-out",
              allDone && "bg-strong"
            )}
            style={{ width: `${overallPercent}%` }}
          />
        </div>
        <ModuleProgressList
          modules={scopedModules}
          progress={progress}
          completed={completedModules}
          activeModule={activeModule}
        />
      </div>
    </ContentContainer>
  );
}
