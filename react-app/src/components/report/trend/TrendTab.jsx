import { useEffect, useMemo, useState } from "react";
import { useAppState } from "../../../state/AppContext";
import * as api from "../../../data/client";
import LoadingState from "../../shared/LoadingState";
import Dropdown from "../../shared/Dropdown";
import LineChart, { trendSeriesColor } from "./LineChart";
import { formatDelta } from "../../../utils/format";
import { DOMAIN_LABELS } from "../../../utils/bands";
import { TREND_GRAINS, bucketTrendSeries } from "./trendGrain";
import { cn } from "@/lib/utils";

function TrendEmpty({ eyebrow, title, children, role }) {
  return (
    <div className="flex min-w-0 flex-col py-6 pb-12 @max-[640px]:py-4 @max-[640px]:pb-8">
      <section className="min-w-0" role={role}>
        <p className="eyebrow">{eyebrow}</p>
        <h1 className="mt-1 font-heading text-lg font-semibold tracking-tight text-ink">
          {title}
        </h1>
        <p className="mt-2 max-w-[46ch] text-xs leading-normal text-ink-soft">
          {children}
        </p>
      </section>
    </div>
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
        series: bucketTrendSeries(group.series, grain),
      }))
      .filter((group) => group.series.length);
  }, [data, grain]);

  if (error) {
    return (
      <TrendEmpty
        eyebrow="Trend unavailable"
        title="The stored scan history could not be compared"
        role="alert"
      >
        {error}
      </TrendEmpty>
    );
  }
  if (!data) return <LoadingState label="Loading trend" />;
  if (seriesGroups.length === 0) {
    return (
      <TrendEmpty
        eyebrow="Score over time"
        title="No measurable trend is available yet"
      >
        Complete a non-empty scan with the same modules, clock, and depth to
        create a comparable point.
      </TrendEmpty>
    );
  }

  const allPoints = seriesGroups
    .flatMap((group) => group.series)
    .sort((left, right) => new Date(left.timestamp) - new Date(right.timestamp));
  const combinedSeries = bucketTrendSeries(data.series ?? [], grain);
  const summarySeries = combinedSeries.length ? combinedSeries : allPoints;
  const average = summarySeries.reduce((sum, point) => sum + point.score, 0) / summarySeries.length;
  const first = allPoints[0];
  const last = allPoints[allPoints.length - 1];
  const delta = last.score - first.score;
  const latest = summarySeries[summarySeries.length - 1];
  const latestDomains = [
    "completeness",
    "duplication",
    "validity",
    "plausibility",
    "freshness",
    "integrity",
    "config",
    "pii",
    "automation",
  ].filter((domain) => latest.measuredDomains?.includes(domain));

  return (
    <div className="flex min-w-0 flex-col py-6 pb-12 @max-[640px]:py-4 @max-[640px]:pb-8">
      <section className="min-w-0">
        <header className="mb-3 flex flex-wrap items-start justify-between gap-3">
          <p className="eyebrow">Score over time</p>
          <Dropdown
            label="Grain"
            value={grain}
            options={TREND_GRAINS}
            onChange={setGrain}
          />
        </header>

        <div
          className="mb-2 flex flex-wrap justify-end gap-x-3.5 gap-y-2"
          aria-label="Chart series"
        >
          {seriesGroups.map((group, index) => (
            <span
              key={group.moduleApiName}
              className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-ink-soft"
            >
              <i
                className="size-[9px] shrink-0 rounded-full not-italic"
                style={{ background: trendSeriesColor(index) }}
                aria-hidden="true"
              />
              {group.moduleApiName}
            </span>
          ))}
        </div>

        <LineChart
          seriesGroups={seriesGroups}
          averageScore={seriesGroups.length === 1 ? average : null}
        />

        <p className="mt-4 text-xs leading-normal text-ink-soft">
          {seriesGroups.length === 1 ? (
            <>
              <span className="mono">{first.score}</span> in {first.period} to{" "}
              <span className="mono">{last.score}</span> in {last.period}{" "}
              (
              <span className={cn("font-bold", delta >= 0 ? "text-strong" : "text-risk")}>
                {formatDelta(delta)}
              </span>
              ) &middot; period average{" "}
              <span className="mono">{average.toFixed(1)}</span>
            </>
          ) : (
            <>
              Comparing <strong>{seriesGroups.length} modules</strong> from {first.period} to {last.period}.
              {combinedSeries.length > 0 && (
                <> Combined period average <span className="mono">{average.toFixed(1)}</span>.</>
              )}
            </>
          )}
        </p>

        <div
          className="mt-5 grid grid-cols-3 gap-x-6 gap-y-4 border-y border-line py-5 @max-[640px]:grid-cols-1"
          aria-label="Latest scan metrics"
        >
          <div className="flex min-w-0 flex-col gap-0.5">
            <span className="text-[11px] font-semibold tracking-wide text-ink-muted uppercase">
              Records
            </span>
            <strong className="mono text-[clamp(16px,1.7cqi,24px)] tracking-tight text-ink">
              {latest.recordCount.toLocaleString("en-IN")}
            </strong>
          </div>
          {latestDomains.map((domain) => (
            <div key={domain} className="flex min-w-0 flex-col gap-0.5">
              <span className="text-[11px] font-semibold tracking-wide text-ink-muted uppercase">
                {DOMAIN_LABELS[domain]}
              </span>
              <strong className="mono text-[clamp(16px,1.7cqi,24px)] tracking-tight text-ink">
                {latest[domain]}
              </strong>
            </div>
          ))}
        </div>

        {allPoints.length === 1 && (
          <p className="mt-3 mb-0 text-xs text-ink-soft">
            One comparable scan is available. A second scan will establish change.
          </p>
        )}
        {data.skippedUnmeasuredCount > 0 && (
          <p className="mt-3 mb-0 text-xs text-ink-soft">
            {data.skippedUnmeasuredCount} empty or incompatible completed scan(s) were not scored.
          </p>
        )}
      </section>
    </div>
  );
}
