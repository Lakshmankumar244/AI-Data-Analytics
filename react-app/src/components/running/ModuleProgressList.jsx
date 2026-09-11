import { formatNumber } from "../../utils/format";
import { cn } from "@/lib/utils";

const PHASE_LABEL = {
  preparing: "Preparing scan",
  submitting: "Submitting to CRM",
  waiting: "Waiting for CRM",
  downloading: "Downloading data",
  processing: "Processing records",
  completed: "Completed",
  failed: "Failed",
};

function recordLine(p, isDone) {
  const scanned = p?.scanned ?? 0;
  const total = p?.estimatedTotal || 0;
  const batchesCompleted = p?.batchesCompleted || 0;
  const batchesTotal = p?.batchesTotal || 0;

  if (isDone && !total && !scanned) return "0 records in range";

  const parts = [];
  if (total) {
    parts.push(`${formatNumber(scanned)} / ${formatNumber(total)} records`);
  } else if (scanned) {
    parts.push(`${formatNumber(scanned)} records processed`);
  }
  if (batchesTotal) {
    parts.push(`${formatNumber(batchesCompleted)} / ${formatNumber(batchesTotal)} batches`);
  }
  return parts.join(" · ");
}

export default function ModuleProgressList({
  modules,
  progress,
  completed,
  activeModule,
}) {
  return (
    <ul className="m-0 flex list-none flex-col gap-4 p-0">
      {modules.map((mod) => {
        const p = progress[mod.apiName];
        const isDone = completed.includes(mod.apiName);
        const isActive = !isDone && activeModule === mod.apiName;
        const isQueued = !isDone && !isActive;
        const pct = isDone ? 100 : Number(p?.percent) || 0;
        const detail = recordLine(p, isDone);

        return (
          <li
            key={mod.apiName}
            className={cn(
              "min-w-0 rounded-md border px-4 py-3",
              isActive
                ? "border-brand bg-[color-mix(in_srgb,var(--brand-soft)_55%,transparent)]"
                : "border-transparent bg-transparent px-0"
            )}
          >
            <div className="mb-2 flex items-baseline justify-between gap-4">
              <span className="flex min-w-0 items-baseline gap-2">
                <span className="text-sm font-semibold text-ink">{mod.label}</span>
                {isActive && (
                  <span className="eyebrow text-brand-strong motion-safe:animate-pulse">
                    Current
                  </span>
                )}
              </span>
              <span
                className={cn(
                  "eyebrow",
                  isDone && "text-strong",
                  isActive && "text-brand-strong",
                  isQueued && "text-ink-muted"
                )}
              >
                {isDone
                  ? "Completed"
                  : isQueued
                  ? "Queued"
                  : PHASE_LABEL[p?.phase] ?? "In progress"}
              </span>
            </div>
            <div className="h-1.5 overflow-hidden bg-surface-sunken">
              <div
                className={cn(
                  "h-full origin-left transition-[width] duration-500 ease-out",
                  isDone && "bg-strong",
                  isActive && "bg-brand",
                  isQueued && "bg-ink-muted"
                )}
                style={{ width: `${pct}%` }}
              />
            </div>
            {detail && (
              <div className="mono mt-1.5 text-xs text-ink-muted">{detail}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
