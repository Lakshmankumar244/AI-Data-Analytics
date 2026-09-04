import { CalendarRange } from "lucide-react";
import { orgBand } from "../../../utils/bands";
import { formatNumber } from "../../../utils/format";
import OverviewEmptyNote from "./OverviewEmptyNote";

export default function OverviewCreatedPeriod({
  series = [],
  periodFrom,
  periodTo,
  clockLabel,
  depthLabel,
}) {
  const hasPeriodFacts = Boolean(periodFrom || periodTo || clockLabel || depthLabel);
  const maxCount = series.reduce(
    (highest, item) => Math.max(highest, Number(item.recordCount) || 0),
    0
  );
  const totalCount = series.reduce(
    (sum, item) => sum + (Number(item.recordCount) || 0),
    0
  );
  const hasVolume = series.length > 0 && maxCount > 0;

  return (
    <section className="panel overview-created-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Created in period</p>
          <h2>Volume over time</h2>
        </div>
        <CalendarRange className="overview-panel-icon" aria-hidden="true" />
      </div>
      <div className="overview-context-body">
        {hasVolume ? (
          <div className="overview-volume-chart" role="img" aria-label="Records created in period by module">
            {series.map((item) => {
              const count = Number(item.recordCount) || 0;
              const height = maxCount ? (count / maxCount) * 100 : 0;
              const band = item.score === null || item.score === undefined
                ? null
                : orgBand(item.score);
              return (
                <div key={item.moduleApiName} className="overview-volume-col">
                  <div className="overview-volume-track">
                    <div
                      className="overview-volume-bar"
                      style={{
                        height: `${height}%`,
                        background: band?.color || "var(--brand)",
                      }}
                      title={`${item.label}: ${formatNumber(count)} records`}
                    />
                  </div>
                  <span className="overview-volume-label" title={item.label}>
                    {item.label}
                  </span>
                </div>
              );
            })}
          </div>
        ) : (
          <OverviewEmptyNote>
            No records were counted in this period, so a volume chart cannot be
            drawn.
          </OverviewEmptyNote>
        )}
      </div>
      {hasPeriodFacts && (
        <dl className="overview-period-facts">
          {(periodFrom || periodTo) && (
            <div>
              <dt>Period</dt>
              <dd className="mono">
                {periodFrom || "—"} – {periodTo || "—"}
              </dd>
            </div>
          )}
          {clockLabel && (
            <div>
              <dt>Attribution</dt>
              <dd>{clockLabel}</dd>
            </div>
          )}
          {depthLabel && (
            <div>
              <dt>Depth</dt>
              <dd>{depthLabel}</dd>
            </div>
          )}
          {hasVolume && (
            <div>
              <dt>Records</dt>
              <dd className="mono">{formatNumber(totalCount)}</dd>
            </div>
          )}
        </dl>
      )}
    </section>
  );
}
