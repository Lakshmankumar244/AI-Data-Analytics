import { formatNumber } from "../../../utils/format";

export default function OverviewKpiCard({
  label,
  value,
  hint,
  detail,
  tone = "neutral",
  icon: Icon,
  action,
  unavailableLabel = "Not measured",
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
      <strong className={unavailable ? undefined : "mono"}>
        {unavailable ? unavailableLabel : formatNumber(value)}
      </strong>
      {detail && !unavailable && <p className="overview-kpi-detail">{detail}</p>}
      {hint && <p className="overview-kpi-hint">{hint}</p>}
      {action && (
        <button type="button" className="overview-kpi-action" onClick={action.onClick}>
          {action.label}
        </button>
      )}
    </article>
  );
}
