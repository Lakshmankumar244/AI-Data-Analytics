import { orgBand } from "../../utils/bands";

/**
 * One row: label, horizontal fill bar, numeric score. Used for each domain
 * on the Overview tab. Colored using the same org-verdict band ramp as the
 * main gauge, since a domain score lives on the same 0-100 "how healthy"
 * scale as the overall score - one color language throughout, not a
 * separate palette per screen.
 */
export default function ScoreBar({ label, score, applicable = true, reason }) {
  if (!applicable) {
    return (
      <div
        className="grid min-w-0 grid-cols-[minmax(0,9.5rem)_minmax(0,1fr)_2.25rem] items-center gap-3 border-t border-line py-[11px] first-of-type:border-t-0 @max-[480px]:grid-cols-[minmax(0,1fr)_2.25rem] @max-[480px]:grid-rows-[auto_auto] @max-[480px]:gap-2"
        title={reason}
      >
        <span className="min-w-0 truncate text-[13px] font-medium text-ink-muted @max-[480px]:col-span-full @max-[480px]:whitespace-normal">
          {label}
        </span>
        <div className="relative h-2 min-w-0 overflow-hidden rounded-full bg-surface-sunken">
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

  return (
    <div className="grid min-w-0 grid-cols-[minmax(0,9.5rem)_minmax(0,1fr)_2.25rem] items-center gap-3 border-t border-line py-[11px] first-of-type:border-t-0 @max-[480px]:grid-cols-[minmax(0,1fr)_2.25rem] @max-[480px]:grid-rows-[auto_auto] @max-[480px]:gap-2">
      <span className="min-w-0 truncate text-[13px] font-medium text-ink-soft @max-[480px]:col-span-full @max-[480px]:whitespace-normal">
        {label}
      </span>
      <div className="relative h-2 min-w-0 overflow-hidden rounded-full bg-surface-sunken">
        <div
          className="h-full rounded-full transition-[width] duration-300"
          style={{ width: `${score}%`, background: band.color }}
        />
      </div>
      <span className="mono text-right text-[13px] font-semibold text-ink">{score}</span>
    </div>
  );
}
