import { formatNumber, formatSeconds } from "../../utils/format";

function DockStat({ label, children }) {
  return (
    <div className="min-w-0">
      <p className="eyebrow">{label}</p>
      <p className="mt-1 text-[13px] font-medium text-ink">{children}</p>
    </div>
  );
}

export default function CostEstimate({ estimate, loading }) {
  if (loading || !estimate) {
    return (
      <div className="col-span-2 min-w-0 sm:col-span-2">
        <p className="eyebrow">Estimate</p>
        <p className="mt-1 text-[13px] text-ink-muted">Calculating{"\u2026"}</p>
      </div>
    );
  }

  return (
    <>
      <DockStat label="Records">
        <span className="mono">{formatNumber(estimate.recordsInRange)}</span>
      </DockStat>
      <DockStat label="Runtime">
        <span className="mono">{formatSeconds(estimate.estimatedRuntimeSeconds)}</span>
        <span className="ml-1.5 font-normal text-ink-muted">
          {formatNumber(estimate.estimatedApiCalls)} API calls
        </span>
      </DockStat>
    </>
  );
}
