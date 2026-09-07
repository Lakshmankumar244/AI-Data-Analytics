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
  const periodLabel =
    periodFrom || periodTo ? `${periodFrom || "—"} – ${periodTo || "—"}` : null;
  const meta = [periodLabel, clockLabel, depthLabel].filter(Boolean);
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
    <div className="flex h-full min-h-0 min-w-0 flex-col">
      <header className="mb-4 shrink-0 border-b border-line pb-3">
        <h2 className="font-heading text-xl font-semibold tracking-tight text-ink">
          Created in period
        </h2>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1">
        {hasVolume ? (
          <div
            className="flex h-full min-h-[148px] items-stretch gap-2 overflow-x-auto bg-surface-sunken px-3 py-3"
            role="img"
            aria-label="Records created in period by module"
          >
            {series.map((item) => {
              const count = Number(item.recordCount) || 0;
              const height = maxCount ? (count / maxCount) * 100 : 0;
              const band =
                item.score === null || item.score === undefined
                  ? null
                  : orgBand(item.score);
              return (
                <div
                  key={item.moduleApiName}
                  className="flex min-w-8 max-w-14 flex-1 flex-col items-center gap-1.5"
                >
                  <div className="flex min-h-[120px] w-full flex-1 items-end">
                    <div
                      className="w-full min-h-[4px]"
                      style={{
                        height: `${height}%`,
                        background: band?.color || "var(--brand)",
                      }}
                      title={`${item.label}: ${formatNumber(count)} records`}
                    />
                  </div>
                  <span
                    className="max-w-full truncate text-center text-[11px] font-medium text-ink-muted"
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
      {(meta.length > 0 || hasVolume) && (
        <p className="mt-3 shrink-0 text-[12px] leading-relaxed text-ink-muted">
          {meta.join(" · ")}
          {hasVolume ? `${meta.length ? " · " : ""}${formatNumber(totalCount)} records` : ""}
        </p>
      )}
    </div>
  );
}
