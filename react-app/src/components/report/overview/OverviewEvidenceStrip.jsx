import { formatNumber } from "../../../utils/format";

function Fact({ label, value, display, hint }) {
  return (
    <div className="overview-evidence-fact">
      <span>{label}</span>
      <strong className="mono">{display ?? formatNumber(value)}</strong>
      {hint && <em>{hint}</em>}
    </div>
  );
}

export default function OverviewEvidenceStrip({
  recordsInScope,
  duplicateCount,
  moduleCount,
  measuredPoints,
  possiblePoints,
}) {
  const coverageReady =
    Number.isFinite(measuredPoints) && Number.isFinite(possiblePoints);

  return (
    <section className="overview-evidence" aria-label="Supporting measurements">
      <Fact label="Records checked" value={recordsInScope} />
      <Fact
        label="Duplicates"
        value={duplicateCount}
        hint={
          duplicateCount === null ? "Not measured in this scan" : undefined
        }
      />
      <Fact label="Modules scanned" value={moduleCount} />
      <Fact
        label="Coverage"
        display={
          coverageReady
            ? `${formatNumber(measuredPoints)}/${formatNumber(possiblePoints)}`
            : formatNumber(null)
        }
        hint={coverageReady ? "Measured points" : "Not available"}
      />
    </section>
  );
}
