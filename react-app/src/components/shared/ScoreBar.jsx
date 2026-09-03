import { orgBand } from "../../utils/bands";
import "./ScoreBar.css";

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
      <div className="score-bar-row score-bar-row-na" title={reason}>
        <span className="score-bar-label">{label}</span>
        <div className="score-bar-track">
          <span className="score-bar-na-text">Not measured</span>
        </div>
        <span className="score-bar-value mono">—</span>
      </div>
    );
  }

  const band = orgBand(score);

  return (
    <div className="score-bar-row">
      <span className="score-bar-label">{label}</span>
      <div className="score-bar-track">
        <div
          className="score-bar-fill"
          style={{ width: `${score}%`, background: band.color }}
        />
      </div>
      <span className="score-bar-value mono">{score}</span>
    </div>
  );
}
