import { formatNumber } from "../../../utils/format";

export default function OverviewKpiCard({
  label,
  value,
  hint,
  tone = "neutral",
  icon: Icon,
}) {
  const unavailable = value === null || value === undefined;

  return (
    <article
      className={`overview-kpi overview-kpi-${tone}${unavailable ? " overview-kpi-empty" : ""}`}
    >
      <div className="overview-kpi-head">
        {Icon && (
          <span className="overview-kpi-icon" aria-hidden="true">
            <Icon strokeWidth={1.75} />
          </span>
        )}
        <span>{label}</span>
      </div>
      <strong className="mono">{unavailable ? formatNumber(null) : formatNumber(value)}</strong>
      {hint && <p className="overview-kpi-hint">{hint}</p>}
    </article>
  );
}
