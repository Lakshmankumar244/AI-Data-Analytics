import { orgBand } from "../../utils/bands";
import { formatDelta } from "../../utils/format";
import Band from "./Band";
import "./ScoreGauge.css";

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
    <div className="score-gauge">
      <div className="score-gauge-ring-wrap">
        <svg viewBox="0 0 120 120" className="score-gauge-ring" role="img" aria-label={`Overall score ${score} out of 100, ${band.label}`}>
          <circle cx="60" cy="60" r={RADIUS} className="score-gauge-track" />
          <circle
            cx="60"
            cy="60"
            r={RADIUS}
            className="score-gauge-fill"
            style={{
              stroke: band.color,
              strokeDasharray: CIRCUMFERENCE,
              strokeDashoffset: offset,
            }}
          />
        </svg>
        <div className="score-gauge-center">
          <span className="score-gauge-number mono">{score}</span>
          <span className="score-gauge-scale mono">/100</span>
        </div>
      </div>

      <div className="score-gauge-meta">
        <Band band={band} size="lg" />

        {delta !== null && (
          <p className={`score-gauge-delta score-gauge-delta-${deltaDirection}`}>
            <span className="mono">{formatDelta(delta)}</span> vs. last check
          </p>
        )}

        <p className="score-gauge-disclosure">
          <span className="mono">{measuredPoints}</span> of{" "}
          <span className="mono">{possiblePoints}</span> possible points measured
          {!isFullyMeasured && unmeasuredDomains.length > 0 && (
            <>
              {" "}
              —{" "}
              {unmeasuredDomains.map((d, i) => (
                <span key={d.domain}>
                  {i > 0 && ", "}
                  <span className="score-gauge-unmeasured-domain" title={d.reason}>
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
