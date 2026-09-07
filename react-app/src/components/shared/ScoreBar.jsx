import { orgBand } from "../../utils/bands";
import { cn } from "@/lib/utils";

/**
 * One quality dimension: label, fill, score. Same 0–100 band language as
 * the overall gauge. Weak scores read heavier than healthy ones.
 */
export default function ScoreBar({ label, score, applicable = true, reason }) {
  if (!applicable) {
    return (
      <div className="flex min-w-0 flex-col gap-1.5 py-2" title={reason}>
        <div className="flex items-baseline justify-between gap-3">
          <span className="min-w-0 truncate text-[13px] font-medium text-ink-muted">
            {label}
          </span>
          <span className="mono shrink-0 text-[13px] font-semibold text-ink-muted">
            n/a
          </span>
        </div>
        <div className="h-1 bg-surface-sunken" />
      </div>
    );
  }

  const band = orgBand(score);
  const needsAttention = band.id === "attention" || band.id === "risk";

  return (
    <div className="flex min-w-0 flex-col gap-1.5 py-2">
      <div className="flex items-baseline justify-between gap-3">
        <span
          className={cn(
            "min-w-0 truncate text-[13px]",
            needsAttention ? "font-semibold text-ink" : "font-medium text-ink-soft"
          )}
        >
          {label}
        </span>
        <span
          className="mono shrink-0 text-[15px] font-semibold tracking-tight"
          style={{ color: needsAttention ? band.color : "var(--ink)" }}
        >
          {score}
        </span>
      </div>
      <div className="h-1 overflow-hidden bg-surface-sunken">
        <div
          className="h-full transition-[width] duration-300"
          style={{
            width: `${score}%`,
            background: band.color,
            opacity: needsAttention ? 1 : 0.85,
          }}
        />
      </div>
    </div>
  );
}
