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
    <section className="flex h-[380px] min-w-0 flex-col overflow-hidden">
      <header className="mb-3 flex shrink-0 items-start justify-between gap-3">
        <div>
          <p className="eyebrow">Created in period</p>
          <h2 className="mt-1 font-heading text-lg font-semibold tracking-tight text-ink">
            Volume over time
          </h2>
        </div>
        <CalendarRange className="size-[18px] shrink-0 text-ink-muted" aria-hidden="true" />
      </header>
      <div className="min-h-0 flex-1 overflow-auto">
        {hasVolume ? (
          <div
            className="flex h-full min-h-[148px] items-stretch gap-2.5 overflow-x-auto overflow-y-hidden pt-1"
            role="img"
            aria-label="Records created in period by module"
          >
            {series.map((item) => {
              const count = Number(item.recordCount) || 0;
              const height = maxCount ? (count / maxCount) * 100 : 0;
              const band = item.score === null || item.score === undefined
                ? null
                : orgBand(item.score);
              return (
                <div
                  key={item.moduleApiName}
                  className="flex min-w-9 max-w-16 flex-1 flex-col items-center gap-2"
                >
                  <div className="flex min-h-28 w-full flex-1 items-end">
                    <div
                      className="w-full min-h-[3px] rounded-t-md"
                      style={{
                        height: `${height}%`,
                        background: band?.color || "var(--brand)",
                      }}
                      title={`${item.label}: ${formatNumber(count)} records`}
                    />
                  </div>
                  <span
                    className="max-w-full truncate text-center text-[11px] font-semibold text-ink-muted"
                    title={item.label}
                  >
                    {item.label}
                  </span>
                </div>
              );
            })}
          </div>
        ) : (
          <OverviewEmptyNote fill>
            No records were counted in this period, so a volume chart cannot be
            drawn.
          </OverviewEmptyNote>
        )}
      </div>
      {hasPeriodFacts && (
        <dl className="mt-3 mb-0 flex shrink-0 flex-col">
          {(periodFrom || periodTo) && (
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2 border-t border-line py-1">
              <dt className="text-xs font-semibold tracking-wide text-ink-muted uppercase">
                Period
              </dt>
              <dd className="mono m-0 text-right text-[13px] font-semibold text-ink">
                {periodFrom || "—"} – {periodTo || "—"}
              </dd>
            </div>
          )}
          {clockLabel && (
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2 border-t border-line py-1">
              <dt className="text-xs font-semibold tracking-wide text-ink-muted uppercase">
                Attribution
              </dt>
              <dd className="m-0 text-right text-[13px] font-semibold text-ink">
                {clockLabel}
              </dd>
            </div>
          )}
          {depthLabel && (
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2 border-t border-line py-1">
              <dt className="text-xs font-semibold tracking-wide text-ink-muted uppercase">
                Depth
              </dt>
              <dd className="m-0 text-right text-[13px] font-semibold text-ink">
                {depthLabel}
              </dd>
            </div>
          )}
          {hasVolume && (
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2 border-t border-line py-1">
              <dt className="text-xs font-semibold tracking-wide text-ink-muted uppercase">
                Records
              </dt>
              <dd className="mono m-0 text-right text-[13px] font-semibold text-ink">
                {formatNumber(totalCount)}
              </dd>
            </div>
          )}
        </dl>
      )}
    </section>
  );
}
