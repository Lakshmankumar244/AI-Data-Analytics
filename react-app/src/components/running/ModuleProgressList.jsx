import { formatNumber } from "../../utils/format";

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
    <ul className="progress-list">
      {modules.map((mod) => {
        const p = progress[mod.apiName];
        const isDone = completed.includes(mod.apiName);
        const isActive = !isDone && activeModule === mod.apiName;
        const isQueued = !isDone && !isActive;
        const pct = isDone ? 100 : isActive ? p?.percent ?? 4 : 0;
        const exactTotal = p?.estimatedTotal || 0;

        return (
          <li key={mod.apiName} className="progress-row">
            <div className="progress-row-top">
              <span className="progress-row-name">{mod.label}</span>
              <span className="progress-row-phase eyebrow">
                {isDone
                  ? "Done"
                  : isQueued
                  ? "Queued"
                  : PHASE_LABEL[p?.phase] ?? "In progress"}
              </span>
            </div>
            <div className="progress-track">
              <div
                className={`progress-fill${isDone ? " progress-fill-done" : ""}${isActive ? " progress-fill-active" : ""}`}
                style={{ width: `${pct}%` }}
              />
            </div>
            <div className="progress-row-count mono">
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
