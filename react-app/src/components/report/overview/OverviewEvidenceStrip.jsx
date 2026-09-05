import { formatNumber } from "../../../utils/format";
import { cn } from "@/lib/utils";

function Fact({ label, value, display, hint, unavailableLabel = "Not measured" }) {
  const unavailable = value === null || value === undefined;
  const shown = display ?? (unavailable ? unavailableLabel : formatNumber(value));
  const empty = unavailable && !display;

  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <span className="text-[11px] font-semibold tracking-wide text-ink-muted uppercase">
        {label}
      </span>
      <strong
        className={cn(
          empty
            ? "text-[13px] font-semibold tracking-normal text-ink-muted"
            : "mono text-[clamp(16px,1.7cqi,20px)] tracking-tight text-ink"
        )}
      >
        {shown}
      </strong>
      {hint && (
        <em className="text-[11px] leading-snug font-normal not-italic text-ink-muted">
          {hint}
        </em>
      )}
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
    <section
      className="grid min-w-0 grid-cols-4 gap-x-6 gap-y-4 border-y border-line py-5 @max-[760px]:grid-cols-2 @max-[560px]:grid-cols-1"
      aria-label="Supporting measurements"
    >
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
