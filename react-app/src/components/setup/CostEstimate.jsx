import { formatNumber, formatSeconds } from "../../utils/format";

function DockStat({ label, children }) {
  return (
    <div className="min-w-0">
      <p className="eyebrow">{label}</p>
      <p className="mt-1 text-[13px] font-medium text-ink">{children}</p>
    </div>
  );
}

function runtimeLabel(estimate) {
  const minSeconds = Number(estimate.estimatedRuntimeMinSeconds) || 0;
  const maxSeconds = Number(estimate.estimatedRuntimeMaxSeconds) || 0;
  if (!minSeconds && !maxSeconds) return "—";
  const minLabel = formatSeconds(minSeconds);
  const maxLabel = formatSeconds(maxSeconds);
  if (minLabel === maxLabel) return `About ${minLabel}`;
  return `${minLabel}–${maxLabel}`;
}

export default function CostEstimate({ estimate, loading, showApiCredits = true }) {
  if (loading || !estimate) {
    return (
      <div className="col-span-2 min-w-0 sm:col-span-2">
        <p className="eyebrow">Estimate</p>
        <p className="mt-1 text-[13px] text-ink-muted">Calculating{"\u2026"}</p>
      </div>
    );
  }

  const credits = Number(
    estimate.estimatedApiCredits ?? estimate.estimatedApiCalls ?? 0
  );

  return (
    <>
      <DockStat label="Records">
        <span className="mono">
          {estimate.recordsKnown
            ? formatNumber(estimate.recordsInRange)
            : "—"}
        </span>
      </DockStat>
      <DockStat label="Runtime">
        <span className="mono">{runtimeLabel(estimate)}</span>
        {showApiCredits ? (
          <span className="ml-1.5 font-normal text-ink-muted">
            {formatNumber(credits)} API credits
          </span>
        ) : null}
      </DockStat>
    </>
  );
}
