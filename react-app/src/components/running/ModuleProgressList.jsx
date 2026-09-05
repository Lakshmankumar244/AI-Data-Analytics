import { formatNumber } from "../../utils/format";
import { cn } from "@/lib/utils";

const PHASE_LABEL = {
  planning: "Planning",
  extracting: "Extracting",
  preparing: "Preparing batches",
  classifying: "Classifying",
  done: "Done",
};

export default function ModuleProgressList({
  modules,
  progress,
  completed,
  activeModule,
}) {
  return (
    <ul className="m-0 flex list-none flex-col gap-6 p-0">
      {modules.map((mod) => {
        const p = progress[mod.apiName];
        const isDone = completed.includes(mod.apiName);
        const isActive = !isDone && activeModule === mod.apiName;
        const isQueued = !isDone && !isActive;
        const pct = isDone ? 100 : isActive ? p?.percent ?? 4 : 0;
        const exactTotal = p?.estimatedTotal || 0;

        return (
          <li key={mod.apiName} className="min-w-0">
            <div className="mb-2 flex items-baseline justify-between gap-4">
              <span className="text-sm font-semibold text-ink">{mod.label}</span>
              <span
                className={cn(
                  "eyebrow",
                  isDone && "text-strong",
                  isActive && "text-brand-strong",
                  isQueued && "text-ink-muted"
                )}
              >
                {isDone
                  ? "Done"
                  : isQueued
                  ? "Queued"
                  : PHASE_LABEL[p?.phase] ?? "In progress"}
              </span>
            </div>
            <div className="h-1.5 overflow-hidden bg-surface-sunken">
              <div
                className={cn(
                  "h-full origin-left transition-[width] duration-300 ease-out",
                  isDone ? "bg-strong" : "bg-brand",
                  isActive && "motion-safe:animate-pulse"
                )}
                style={{ width: `${pct}%` }}
              />
            </div>
            <div className="mono mt-1.5 text-xs text-ink-muted">
              {isQueued
                ? "Waiting to start"
                : isDone && !exactTotal
                ? "0 records matched the selected range"
                : exactTotal
                ? `${formatNumber(p?.scanned ?? 0)} / ${formatNumber(exactTotal)} records`
                : mod.recordCount
                ? `Preparing up to ${formatNumber(mod.recordCount)} records`
                : "Preparing record count"}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
