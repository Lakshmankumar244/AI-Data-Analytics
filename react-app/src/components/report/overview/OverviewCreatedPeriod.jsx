import { CalendarRange } from "lucide-react";
import OverviewEmptyNote from "./OverviewEmptyNote";

export default function OverviewCreatedPeriod({
  periodFrom,
  periodTo,
  clockLabel,
  depthLabel,
}) {
  const hasPeriodFacts = Boolean(periodFrom || periodTo || clockLabel || depthLabel);

  return (
    <section className="panel overview-created-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Created in period</p>
          <h2>Volume over time</h2>
        </div>
        <CalendarRange className="overview-panel-icon" aria-hidden="true" />
      </div>
      <OverviewEmptyNote>
        Daily creation volume is not included in this scan, so a period chart
        cannot be drawn.
      </OverviewEmptyNote>
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
        </dl>
      )}
    </section>
  );
}
