import { useEffect, useMemo, useRef, useState } from "react";
import { useAppState, useAppDispatch } from "../../state/AppContext";
import { adaptAnalyticsResults } from "../../data/analyticsAdapter";
import { getScanHistory } from "../../data/client";
import useScanAnalytics from "../../hooks/useScanAnalytics";
import { formatNumber } from "../../utils/format";
import { cn } from "@/lib/utils";
import { ContentContainer } from "../layout";
import { Button } from "@/components/ui/button";
import ModuleProgressList from "./ModuleProgressList";
import {
  STAGE,
  STAGE_FLOW,
  activeModuleFromStatus,
  deriveModuleStage,
  deriveScanStage,
  moduleDisplayProgress,
  progressFromStatus,
} from "./scanStage";

function firstFailureDetail(status) {
  for (const module of status?.modules ?? []) {
    for (const task of module.tasks ?? []) {
      if (task.controlledErrorCode) return String(task.controlledErrorCode);
    }
  }
  return null;
}

function ratioLabel(value, total) {
  if (total > 0) return `${formatNumber(value)} / ${formatNumber(total)}`;
  return formatNumber(value);
}

function LiveStat({ label, children }) {
  return (
    <div className="min-w-0">
      <p className="mono text-2xl font-semibold tracking-tight text-ink">{children}</p>
      <p className="mt-1 text-xs text-ink-muted">{label}</p>
    </div>
  );
}

function StageSteps({ stage }) {
  const currentIndex = STAGE_FLOW.findIndex((item) => item.id === stage.id);
  return (
    <ol className="m-0 flex list-none flex-wrap gap-1 p-0" aria-label="Scan stages">
      {STAGE_FLOW.map((item, index) => {
        const isCurrent = item.id === stage.id;
        const isPast = currentIndex >= 0 && index < currentIndex;
        return (
          <li
            key={item.id}
            className={cn(
              "rounded-full px-1.5 py-0.5 text-[10px] font-semibold tracking-[0.04em] uppercase leading-tight",
              isCurrent && "bg-brand text-on-brand",
              isPast && !isCurrent && "bg-strong-soft text-strong",
              !isCurrent && !isPast && "bg-surface-sunken text-ink-muted"
            )}
            aria-current={isCurrent ? "step" : undefined}
          >
            {item.label}
          </li>
        );
      })}
    </ol>
  );
}

export default function RunningScreen() {
  const { connection, scanConfig, scanId, scanContext } = useAppState();
  const dispatch = useAppDispatch();
  const { status, results, loading, error, refresh, lastAdvance } =
    useScanAnalytics(scanId);
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

  const scopedModules = useMemo(() => {
    const moduleMetadata = new Map(
      (connection?.accessibleModules ?? []).map((module) => [module.apiName, module])
    );
    const fromStatus = (status?.modules ?? [])
      .map((module) => module.moduleApiName)
      .filter(Boolean);
    const apiNames = fromStatus.length ? fromStatus : scanConfig.modules;
    return apiNames.map((apiName) => ({
      apiName,
      label: moduleMetadata.get(apiName)?.label || apiName,
    }));
  }, [connection?.accessibleModules, scanConfig.modules, status?.modules]);

  const stage = deriveScanStage(status);
  const activeModuleRow = activeModuleFromStatus(status);
  const activeModule = activeModuleRow?.moduleApiName ?? null;
  const activeModuleLabel =
    scopedModules.find((module) => module.apiName === activeModule)?.label ||
    activeModule;
  const completedModules = useMemo(
    () =>
      (status?.modules ?? [])
        .filter((module) => module.status === "COMPLETED")
        .map((module) => module.moduleApiName),
    [status]
  );
  const totals = progressFromStatus(status);
  const plannedModuleCount = Math.max(
    totals.plannedModules,
    scopedModules.length
  );

  const progress = useMemo(() => {
    const nextProgress = {};
    for (const module of status?.modules ?? []) {
      const moduleStage = deriveModuleStage(module);
      const done = module.status === "COMPLETED";
      const isActive = !done && module.moduleApiName === activeModule;
      const display = moduleDisplayProgress(module, { isActive, isDone: done });
      nextProgress[module.moduleApiName] = {
        scanned: display.scanned,
        estimatedTotal: display.estimatedTotal,
        batchesCompleted: Number(module.batchesCompleted) || 0,
        batchesTotal: Number(module.batches?.total) || 0,
        phase: moduleStage.id,
        percent: display.percent,
      };
    }
    return nextProgress;
  }, [activeModule, status]);

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
  const isLive = stage.id !== STAGE.completed.id && stage.id !== STAGE.failed.id;
  const canOpenReport = stage.id === STAGE.completed.id && results && !emptyResults;
  const failureDetail = stage.id === STAGE.failed.id ? firstFailureDetail(status) : null;

  useEffect(() => {
    if (status?.status !== "COMPLETED") return undefined;
    let cancelled = false;
    getScanHistory()
      .then((history) => {
        if (!cancelled) {
          dispatch({
            type: "historyLoaded",
            scanHistory: history?.scans ?? [],
          });
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [dispatch, results, status?.status]);

  function openReport() {
    if (!results || !scanId) return;
    dispatch({
      type: "scanComplete",
      scanId,
      scan: {
        ...adaptAnalyticsResults(results),
        ...(scanContext ? { reportContext: scanContext } : {}),
      },
    });
  }

  if (emptyResults) {
    const moduleNames = results.modules
      .map((module) => module.moduleApiName)
      .filter(Boolean)
      .join(", ");
    return (
      <ContentContainer className="flex min-h-full flex-col justify-center py-12 sm:py-16">
        <div className="max-w-[36rem]" aria-labelledby="empty-scan-title">
          <h1
            id="empty-scan-title"
            className="font-heading text-3xl font-semibold tracking-tight text-ink sm:text-4xl"
          >
            No records matched this scan
          </h1>
          <p className="mt-4 max-w-[34rem] text-sm leading-relaxed text-ink-soft">
            {`No ${moduleNames || "CRM"} records for the selected date range and clock.`}
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
    <ContentContainer className="flex min-h-full min-w-0 flex-col pt-6 pb-8 @min-[640px]:pt-8">
      <section className="flex min-w-0 flex-col rounded-md border border-line bg-surface p-5 @min-[640px]:p-6">
        <header className="flex min-w-0 flex-col gap-4 @min-[640px]:flex-row @min-[640px]:items-start @min-[640px]:justify-between @min-[640px]:gap-10">
          <div className="min-w-0 max-w-[42rem]">
            <p className="eyebrow mb-2">Worker status</p>
            <h1 className="flex items-center gap-2 font-heading text-xl font-semibold tracking-tight text-ink sm:text-2xl">
              {isLive && (
                <span
                  className="size-1.5 shrink-0 rounded-full bg-brand motion-safe:animate-pulse"
                  aria-hidden="true"
                />
              )}
              {stage.label}
            </h1>
            <p
              className={cn(
                "mt-2 mb-0 text-[13px]",
                stage.id === STAGE.failed.id ? "text-risk" : "text-ink-soft"
              )}
              role="status"
            >
              {stage.description}
              {isLive && activeModuleLabel ? ` Current module: ${activeModuleLabel}.` : ""}
            </p>
            {failureDetail && (
              <p className="mt-2 mb-0 text-[13px] text-risk" role="alert">
                {failureDetail}
              </p>
            )}
            {error && (
              <p className="mt-2 mb-0 text-[13px] text-risk" role="alert">
                {error}
              </p>
            )}
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            {canOpenReport && (
              <Button type="button" size="lg" onClick={openReport}>
                Open report
              </Button>
            )}
            {(stage.id === STAGE.completed.id || stage.id === STAGE.failed.id) && (
              <Button
                type="button"
                variant={canOpenReport ? "outline" : "default"}
                size="lg"
                onClick={() => dispatch({ type: "showHome" })}
              >
                Back to reports
              </Button>
            )}
            <Button
              type="button"
              variant="outline"
              size="lg"
              disabled={loading}
              onClick={refresh}
            >
              {loading ? "Refreshing…" : "Refresh status"}
            </Button>
          </div>
        </header>

        {stage.id !== STAGE.failed.id && (
          <div className="mt-5">
            <StageSteps stage={stage} />
          </div>
        )}

        <div
          className="mt-5 grid grid-cols-2 overflow-hidden rounded-md border border-line @min-[640px]:grid-cols-3"
          aria-label="Live scan progress"
        >
          <div className="border-b border-line px-4 py-4 @min-[640px]:border-r @min-[640px]:border-b-0">
            <LiveStat label="Modules completed">
              {ratioLabel(totals.completedModules, plannedModuleCount)}
            </LiveStat>
          </div>
          <div className="border-b border-line px-4 py-4 @min-[640px]:border-r @min-[640px]:border-b-0">
            <LiveStat label="API credits used">
              {liveUsage.credits.toLocaleString("en-IN")}
            </LiveStat>
          </div>
          <div className="col-span-2 px-4 py-4 @min-[640px]:col-span-1">
            <LiveStat label="Throttle retries">
              {liveUsage.throttleRetries.toLocaleString("en-IN")}
            </LiveStat>
          </div>
        </div>

        <div className="mt-6 min-w-0">
          <p className="eyebrow mb-4">Modules</p>
          <ModuleProgressList
            modules={scopedModules}
            progress={progress}
            completed={completedModules}
            activeModule={activeModule}
          />
        </div>

        {isLive && (
          <div className="mt-6 flex justify-end border-t border-line pt-4">
            <Button
              type="button"
              variant="outline"
              size="lg"
              className="text-risk hover:bg-risk-soft hover:text-risk"
              onClick={() => dispatch({ type: "reset" })}
            >
              Cancel
            </Button>
          </div>
        )}
      </section>
    </ContentContainer>
  );
}
