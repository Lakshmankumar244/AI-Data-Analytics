import { useEffect, useMemo, useState } from "react";
import { useAppState } from "../../../state/AppContext";
import * as api from "../../../data/client";
import LoadingState from "../../shared/LoadingState";
import Dropdown from "../../shared/Dropdown";
import LineChart, { trendSeriesColor } from "./LineChart";
import { formatDelta, formatNumber } from "../../../utils/format";
import { TREND_GRAINS, bucketTrendSeries } from "./trendGrain";
import { cn } from "@/lib/utils";

function TrendEmpty({ title, children, role }) {
  return (
    <div className="flex min-w-0 flex-col py-6 pb-10 @max-[760px]:py-4 @max-[760px]:pb-8">
      <section className="min-w-0" role={role}>
        <h1 className="font-heading text-xl font-semibold tracking-tight text-ink">
          {title}
        </h1>
        <p className="mt-2 max-w-[46ch] text-sm leading-relaxed text-ink-soft">
          {children}
        </p>
      </section>
    </div>
  );
}

function cohortReading(current, previous) {
  if (!previous) {
    return { label: "Baseline", tone: "neutral" };
  }
  const delta = current.score - previous.score;
  if (delta > 0) {
    return { label: "Better than the cohort before", tone: "up" };
  }
  if (delta < 0) {
    return { label: "Worse than the cohort before", tone: "down" };
  }
  return { label: "Holding", tone: "neutral" };
}

function ReadingBadge({ reading }) {
  if (reading.tone === "neutral") {
    return <span className="text-[13px] text-ink-muted">{reading.label}</span>;
  }
  return (
    <span
      className="inline-flex max-w-full px-1.5 py-0.5 text-[12px] font-semibold tracking-tight"
      style={
        reading.tone === "up"
          ? { background: "var(--strong-soft)", color: "var(--strong)" }
          : { background: "var(--risk-soft)", color: "var(--risk)" }
      }
    >
      {reading.label}
    </span>
  );
}

export default function TrendTab() {
  const { scanId, scan, filterModules } = useAppState();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [grain, setGrain] = useState("month");
  const reportModules = (scan?.moduleFindings ?? []).map((module) => module.apiName);
  const selectedModules = filterModules.length ? filterModules : reportModules;
  const moduleKey = [...selectedModules].sort().join(",");
  const moduleLabels = useMemo(
    () =>
      new Map(
        (scan?.moduleFindings ?? []).map((module) => [module.apiName, module.label])
      ),
    [scan]
  );

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    api
      .getTrend(scanId, selectedModules)
      .then((response) => {
        if (!cancelled) setData(response);
      })
      .catch((requestError) => {
        if (!cancelled) setError(requestError.message);
      });
    return () => {
      cancelled = true;
    };
    // moduleKey is the stable dependency for the selected module set.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scanId, moduleKey]);

  const seriesGroups = useMemo(() => {
    if (!data) return [];
    const rawGroups = (data.moduleSeries?.length
      ? data.moduleSeries
      : [{ moduleApiName: data.criteria.modules.join(" + "), series: data.series }]
    ).filter((group) => group.series?.length);
    return rawGroups
      .map((group) => ({
        ...group,
        label: moduleLabels.get(group.moduleApiName) || group.moduleApiName,
        series: bucketTrendSeries(group.series, grain),
      }))
      .filter((group) => group.series.length);
  }, [data, grain, moduleLabels]);

  if (error) {
    return (
      <TrendEmpty title="Trend unavailable" role="alert">
        {error}
      </TrendEmpty>
    );
  }
  if (!data) return <LoadingState label="Loading trend" />;
  if (seriesGroups.length === 0) {
    return (
      <TrendEmpty title="No measurable trend yet">
        Complete another scan with the same modules, clock, and depth.
      </TrendEmpty>
    );
  }

  const allPoints = seriesGroups
    .flatMap((group) => group.series)
    .sort((left, right) => new Date(left.timestamp) - new Date(right.timestamp));
  const combinedSeries = bucketTrendSeries(data.series ?? [], grain);
  const summarySeries = combinedSeries.length ? combinedSeries : allPoints;
  const average = summarySeries.reduce((sum, point) => sum + point.score, 0) / summarySeries.length;
  const first = summarySeries[0] ?? allPoints[0];
  const last = summarySeries[summarySeries.length - 1] ?? allPoints[allPoints.length - 1];
  const delta = last.score - first.score;
  const deltaTone = delta > 0 ? "up" : delta < 0 ? "down" : undefined;
  const cohorts = summarySeries.map((point, index) => ({
    ...point,
    reading: cohortReading(point, summarySeries[index - 1]),
  }));
  const showAverage = seriesGroups.length === 1;

  return (
    <div className="flex min-w-0 flex-col gap-5 py-4 pb-8 @max-[760px]:py-3 @max-[760px]:pb-6">
      <section className="flex min-w-0 flex-col rounded-md border border-line bg-surface p-5 @min-[640px]:p-6">
        <header className="mb-4 flex shrink-0 flex-wrap items-end justify-between gap-3">
          <h2 className="font-heading text-xl font-semibold tracking-tight text-ink">
            Score over time
          </h2>
          <Dropdown
            label="Grain"
            value={grain}
            options={TREND_GRAINS}
            onChange={setGrain}
          />
        </header>

        <LineChart
          seriesGroups={seriesGroups}
          averageScore={showAverage ? average : null}
        />

        <ul
          className="mt-3 mb-0 flex list-none flex-wrap items-center gap-x-5 gap-y-2 p-0"
          aria-label="Chart series"
        >
          {seriesGroups.map((group, index) => {
            const start = group.series[0];
            const end = group.series[group.series.length - 1];
            const change = end.score - start.score;
            const tone = change > 0 ? "text-strong" : change < 0 ? "text-risk" : "text-ink-muted";
            return (
              <li
                key={group.moduleApiName}
                className="flex min-w-0 items-center gap-2 text-[13px]"
              >
                <i
                  className="inline-block h-px w-4 shrink-0 border-0 not-italic"
                  style={{ background: trendSeriesColor(index), height: 2 }}
                  aria-hidden="true"
                />
                <span className="truncate font-medium text-ink">
                  {group.label || group.moduleApiName}
                </span>
                <span className="mono font-semibold tracking-tight text-ink">
                  {end.score}
                </span>
                <span className={cn("mono font-semibold", tone)}>
                  {formatDelta(change)}
                </span>
              </li>
            );
          })}
          {showAverage && (
            <li className="flex items-center gap-2 text-[13px] text-ink-muted">
              <i
                className="inline-block w-4 shrink-0 border-t border-dashed border-ink-muted not-italic"
                aria-hidden="true"
              />
              <span>Whole scan average ({average.toFixed(1)})</span>
            </li>
          )}
        </ul>

        <aside
          className="mt-4 border-l-[3px] border-brand bg-brand-soft px-4 py-3 text-[13px] font-semibold leading-snug text-brand-strong"
          role="note"
        >
          <span className="mono">{first.period}</span>{" "}
          <span className="mono">{first.score}</span>
          {" → "}
          <span className="mono">{last.period}</span>{" "}
          <span className="mono">{last.score}</span>
          {" · whole scan "}
          <span className="mono">{average.toFixed(1)}</span>
          <span className="sr-only">
            {` Latest ${last.score} ${last.period}. Change ${formatDelta(delta)}${
              deltaTone ? ` ${deltaTone}` : ""
            }. Average ${average.toFixed(1)}.`}
          </span>
        </aside>

        {allPoints.length === 1 && (
          <p className="mt-3 mb-0 text-[13px] text-ink-muted">
            One comparable scan is available.
          </p>
        )}
        {data.skippedUnmeasuredCount > 0 && (
          <p className="mt-3 mb-0 text-[13px] text-ink-muted">
            {data.skippedUnmeasuredCount} empty or incompatible scan(s) were not scored.
          </p>
        )}
      </section>

      <section className="flex min-w-0 flex-col rounded-md border border-line bg-surface p-5 @min-[640px]:p-6">
        <header className="mb-4 border-b border-line pb-3">
          <h2 className="font-heading text-xl font-semibold tracking-tight text-ink">
            Creation cohorts
          </h2>
        </header>
        <div className="min-w-0 overflow-x-auto overscroll-x-contain">
          <table className="w-full min-w-[36rem] border-collapse text-[13px]">
            <caption className="sr-only">
              Creation cohorts with record count, score today, and reading versus
              the previous cohort
            </caption>
            <thead>
              <tr>
                <th className="border-b border-line py-2.5 pr-4 text-left align-middle">
                  <span className="eyebrow">Cohort</span>
                </th>
                <th className="border-b border-line px-3 py-2.5 text-right align-middle">
                  <span className="eyebrow">Records</span>
                </th>
                <th className="border-b border-line px-3 py-2.5 text-right align-middle">
                  <span className="eyebrow">Score today</span>
                </th>
                <th className="border-b border-line py-2.5 pl-3 text-left align-middle">
                  <span className="eyebrow">Reading</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {cohorts.map((cohort) => (
                <tr key={cohort.timestamp}>
                  <th
                    scope="row"
                    className="border-b border-line py-2.5 pr-4 text-left align-middle font-semibold tracking-tight text-ink"
                  >
                    {cohort.period}
                  </th>
                  <td className="mono border-b border-line px-3 py-2.5 text-right text-ink">
                    {formatNumber(cohort.recordCount)}
                  </td>
                  <td className="mono border-b border-line px-3 py-2.5 text-right font-semibold tracking-tight text-ink">
                    {typeof cohort.score === "number" ? cohort.score : "—"}
                  </td>
                  <td className="border-b border-line py-2.5 pl-3">
                    <ReadingBadge reading={cohort.reading} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
