import { orgBand } from "../../utils/bands";
import { cn } from "@/lib/utils";

/**
 * One quality dimension: label, fill, score. Same 0–100 band language as
 * the overall gauge. Weak scores read heavier than healthy ones.
 */
export default function ScoreBar({ label, score, applicable = true, reason }) {
  if (!applicable) {
    return (
      <div
        className="grid min-w-0 grid-cols-[minmax(0,8.5rem)_minmax(0,1fr)_2.5rem] items-center gap-x-3 gap-y-1 py-1.5 @max-[480px]:grid-cols-[minmax(0,1fr)_2.5rem]"
        title={reason}
      >
        <span className="min-w-0 text-[13px] font-medium text-ink-muted @max-[480px]:col-span-full">
          {label}
        </span>
        <div className="relative h-2.5 min-w-0 bg-surface-sunken">
          <span className="absolute top-1/2 left-2 -translate-y-1/2 text-[11px] text-ink-muted italic">
            Not measured
          </span>
        </div>
        <span className="mono text-right text-[13px] font-semibold text-ink-muted">
          —
        </span>
      </div>
    );
  }

  const band = orgBand(score);
  const needsAttention = band.id === "attention" || band.id === "risk";

  return (
    <div className="grid min-w-0 grid-cols-[minmax(0,8.5rem)_minmax(0,1fr)_2.5rem] items-center gap-x-3 gap-y-1 py-1.5 @max-[480px]:grid-cols-[minmax(0,1fr)_2.5rem]">
      <span
        className={cn(
          "min-w-0 text-[13px] @max-[480px]:col-span-full",
          needsAttention ? "font-semibold text-ink" : "font-medium text-ink-soft"
        )}
      >
        {label}
      </span>
      <div className="relative h-2.5 min-w-0 overflow-hidden bg-surface-sunken">
        <div
          className="h-full transition-[width] duration-300"
          style={{
            width: `${score}%`,
            background: band.color,
            opacity: needsAttention ? 1 : 0.72,
          }}
        />
      </div>
      <span
        className="mono text-right text-[15px] font-semibold tracking-tight"
        style={{ color: needsAttention ? band.color : "var(--ink)" }}
      >
        {score}
      </span>
    </div>
  );
}
