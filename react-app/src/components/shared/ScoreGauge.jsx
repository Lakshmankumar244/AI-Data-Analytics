import { orgBand } from "../../utils/bands";
import { formatDelta } from "../../utils/format";
import { cn } from "@/lib/utils";

const RADIUS = 54;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

/**
 * Org-health verdict. The number and band are the story; the ring is the
 * instrument around them. Measured-points disclosure stays required so a
 * partial scan cannot look more complete than it is.
 */
export default function ScoreGauge({
  score,
  priorScore,
  measuredPoints,
  possiblePoints,
  unmeasuredDomains = [],
}) {
  const band = orgBand(score);
  const offset = CIRCUMFERENCE * (1 - score / 100);
  const delta = typeof priorScore === "number" ? score - priorScore : null;
  const deltaDirection = delta > 0 ? "up" : delta < 0 ? "down" : "flat";
  const isFullyMeasured = measuredPoints === possiblePoints;

  return (
    <div className="score-gauge flex min-w-0 flex-wrap items-center gap-x-7 gap-y-4">
      <div className="score-gauge-ring-wrap relative aspect-square w-[min(168px,100%)] shrink-0 grow-0 basis-[168px]">
        <svg
          viewBox="0 0 120 120"
          className="h-full w-full -rotate-90"
          role="img"
          aria-label={`Overall score ${score} out of 100, ${band.label}`}
        >
          <circle
            cx="60"
            cy="60"
            r={RADIUS}
            className="fill-none"
            stroke="var(--surface-sunken)"
            strokeWidth="7"
          />
          <circle
            cx="60"
            cy="60"
            r={RADIUS}
            className="fill-none [transition:stroke-dashoffset_0.5s_ease,stroke_0.3s_ease]"
            strokeWidth="7"
            strokeLinecap="round"
            style={{
              stroke: band.color,
              strokeDasharray: CIRCUMFERENCE,
              strokeDashoffset: offset,
            }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="score-gauge-number mono font-heading text-[clamp(36px,4.4cqi,48px)] leading-none font-bold tracking-[-0.04em] text-ink">
            {score}
          </span>
          <span className="mono mt-0.5 text-[11px] tracking-wide text-ink-muted">
            /100
          </span>
        </div>
      </div>

      <div className="flex min-w-[min(200px,100%)] flex-1 flex-col items-start gap-2">
        <p
          className="m-0 font-heading text-[clamp(22px,2.8cqi,30px)] leading-tight font-semibold tracking-[-0.03em]"
          style={{ color: band.color }}
        >
          {band.label}
        </p>

        {delta !== null && (
          <p
            className={cn(
              "m-0 text-[13px] font-medium",
              deltaDirection === "up" && "text-strong",
              deltaDirection === "down" && "text-risk",
              deltaDirection === "flat" && "text-ink-soft"
            )}
          >
            <span className="mono text-[15px] font-semibold">
              {formatDelta(delta)}
            </span>{" "}
            vs last check
          </p>
        )}

        <p className="m-0 max-w-[40ch] text-[13px] leading-relaxed text-ink-muted">
          <span className="mono">{measuredPoints}</span> of{" "}
          <span className="mono">{possiblePoints}</span> possible points measured
          {!isFullyMeasured && unmeasuredDomains.length > 0 && (
            <>
              {" "}
              —{" "}
              {unmeasuredDomains.map((d, i) => (
                <span key={d.domain}>
                  {i > 0 && ", "}
                  <span
                    className="cursor-help underline decoration-dotted underline-offset-2"
                    title={d.reason}
                  >
                    {d.domain}
                  </span>
                </span>
              ))}{" "}
              not included
            </>
          )}
          .
        </p>
      </div>
    </div>
  );
}
