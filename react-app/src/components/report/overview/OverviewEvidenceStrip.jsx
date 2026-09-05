import { formatNumber } from "../../../utils/format";
import { cn } from "@/lib/utils";

function Fact({ label, value, display, hint, unavailableLabel = "Not measured" }) {
  const unavailable = value === null || value === undefined;
  const shown = display ?? (unavailable ? unavailableLabel : formatNumber(value));
  const empty = unavailable && !display;

  return (
    <div className="min-w-0">
      <span className="eyebrow">{label}</span>
      <strong
        className={cn(
          "mt-1.5 block tracking-tight",
          empty
            ? "text-[13px] font-semibold text-ink-muted"
            : "mono text-[17px] font-semibold text-ink"
        )}
      >
        {shown}
      </strong>
      {hint && (
        <em className="mt-0.5 block text-[11px] leading-snug font-normal not-italic text-ink-muted">
          {hint}
        </em>
      )}
    </div>
  );
}

export default function OverviewEvidenceStrip({
  recordsInScope,
  moduleCount,
  measuredPoints,
  possiblePoints,
}) {
  const coverageReady =
    Number.isFinite(measuredPoints) && Number.isFinite(possiblePoints);

  return (
    <section
      className="grid min-w-0 grid-cols-3 gap-x-8 gap-y-4"
      aria-label="Scan coverage"
    >
      <Fact label="Records checked" value={recordsInScope} />
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
