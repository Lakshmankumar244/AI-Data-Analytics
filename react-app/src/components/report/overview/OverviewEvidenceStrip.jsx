import { formatNumber } from "../../../utils/format";

function Fact({ label, value, display, hint, unavailableLabel = "Not measured" }) {
  const unavailable = value === null || value === undefined;
  const shown = display ?? (unavailable ? unavailableLabel : formatNumber(value));

  return (
    <div className={`overview-evidence-fact${unavailable && !display ? " overview-evidence-fact-empty" : ""}`}>
      <span>{label}</span>
      <strong className={unavailable && !display ? undefined : "mono"}>{shown}</strong>
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
        hint={duplicateCount === null ? undefined : "Duplicate occurrences"}
        unavailableLabel="Not measured"
      />
      <Fact label="Modules scanned" value={moduleCount} />
      <Fact
        label="Coverage"
        display={
          coverageReady
            ? `${formatNumber(measuredPoints)}/${formatNumber(possiblePoints)}`
            : undefined
        }
        value={coverageReady ? measuredPoints : null}
        hint={coverageReady ? "Measured points" : undefined}
        unavailableLabel="Not available"
      />
    </section>
  );
}
