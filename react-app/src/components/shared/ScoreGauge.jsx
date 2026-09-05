import { orgBand } from "../../utils/bands";
import { formatDelta } from "../../utils/format";
import Band from "./Band";
import { cn } from "@/lib/utils";

const RADIUS = 54;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

/**
 * The org-band-style verdict gauge, reused here for the Personal Check score.
 * Always shows the D2b disclosure line ("X of Y possible points measured") —
 * this is not optional decoration, it's the thing that keeps the number
 * honest when a domain (PII, Automation Health) couldn't be measured this run.
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
    <div className="score-gauge flex min-w-0 flex-wrap items-center gap-[clamp(22px,4cqi,48px)]">
      <div className="score-gauge-ring-wrap relative aspect-square w-[min(156px,100%)] shrink-0 grow-0 basis-[156px]">
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
            className="fill-none stroke-surface-sunken"
            strokeWidth="8"
          />
          <circle
            cx="60"
            cy="60"
            r={RADIUS}
            className="fill-none stroke-[8] [stroke-linecap:round] [transition:stroke-dashoffset_0.5s_ease,stroke_0.3s_ease]"
            style={{
              stroke: band.color,
              strokeDasharray: CIRCUMFERENCE,
              strokeDashoffset: offset,
            }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="score-gauge-number mono font-heading text-[clamp(32px,4.2cqi,40px)] leading-none font-bold tracking-tight text-ink">
            {score}
          </span>
          <span className="mono mt-0.5 text-xs text-ink-muted">/100</span>
        </div>
      </div>

      <div className="flex min-w-[min(220px,100%)] flex-col items-start gap-2.5">
        <Band band={band} size="lg" />

        {delta !== null && (
          <p
            className={cn(
              "m-0 text-[13px]",
              deltaDirection === "up" && "text-strong",
              deltaDirection === "down" && "text-risk",
              deltaDirection === "flat" && "text-ink-soft"
            )}
          >
            <span className="mono">{formatDelta(delta)}</span> vs. last check
          </p>
        )}

        <p className="m-0 max-w-[42ch] text-[13px] leading-normal text-ink-muted">
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
