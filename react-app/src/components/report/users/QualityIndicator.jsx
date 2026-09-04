import { orgBand } from "../../../utils/bands";

export default function QualityIndicator({
  label,
  score,
  size = "md",
  emphasize = false,
}) {
  const measured = typeof score === "number";
  const band = measured ? orgBand(score) : null;

  return (
    <div
      className={`quality-indicator quality-indicator-${size}${emphasize ? " quality-indicator-emphasize" : ""}`}
    >
      {label && <span className="quality-indicator-label">{label}</span>}
      <div
        className="quality-indicator-track"
        role="img"
        aria-label={measured ? `${score} out of 100` : "Not measured"}
      >
        {measured ? (
          <span
            className="quality-indicator-fill"
            style={{ width: `${score}%`, background: band.color }}
          />
        ) : null}
      </div>
      <span className="quality-indicator-value mono">
        {measured ? score : "—"}
      </span>
    </div>
  );
}
