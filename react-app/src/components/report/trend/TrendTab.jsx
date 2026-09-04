import { useEffect, useMemo, useState } from "react";
import { useAppState } from "../../../state/AppContext";
import * as api from "../../../data/client";
import LoadingState from "../../shared/LoadingState";
import Dropdown from "../../shared/Dropdown";
import LineChart from "./LineChart";
import { formatDelta } from "../../../utils/format";
import { DOMAIN_LABELS } from "../../../utils/bands";
import { TREND_GRAINS, bucketTrendSeries } from "./trendGrain";
import "./TrendTab.css";

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
      <div className="trend-tab">
        <section className="panel trend-state" role="alert">
          <p className="eyebrow">Trend unavailable</p>
          <h1>The stored scan history could not be compared</h1>
          <p>{error}</p>
        </section>
      </div>
    );
  }
  if (!data) return <LoadingState label="Loading trend" />;
  if (seriesGroups.length === 0) {
    return (
      <div className="trend-tab">
        <section className="panel trend-state">
          <p className="eyebrow">Score over time</p>
          <h1>No measurable trend is available yet</h1>
          <p>
            Complete a non-empty scan with the same modules, clock, and depth to
            create a comparable point.
          </p>
        </section>
      </div>
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
    <div className="trend-tab">
      <section className="panel">
        <div className="panel-header">
          <p className="eyebrow">Score over time</p>
          <Dropdown
            label="Grain"
            value={grain}
            options={TREND_GRAINS}
            onChange={setGrain}
          />
        </div>

        <div className="trend-legend" aria-label="Chart series">
          {seriesGroups.map((group, index) => (
            <span key={group.moduleApiName}>
              <i className={`trend-legend-swatch trend-series-${index % 6}`} />
              {group.moduleApiName}
            </span>
          ))}
        </div>

        <LineChart
          seriesGroups={seriesGroups}
          averageScore={seriesGroups.length === 1 ? average : null}
        />

        <p className="trend-summary">
          {seriesGroups.length === 1 ? (
            <>
              <span className="mono">{first.score}</span> in {first.period} to{" "}
              <span className="mono">{last.score}</span> in {last.period}{" "}
              (<span className={delta >= 0 ? "trend-up" : "trend-down"}>{formatDelta(delta)}</span>) &middot;{" "}
              period average <span className="mono">{average.toFixed(1)}</span>
            </>
          ) : (
            <>
              Comparing <strong>{seriesGroups.length} modules</strong> from {first.period} to {last.period}.
              {combinedSeries.length > 0 && <> Combined period average <span className="mono">{average.toFixed(1)}</span>.</>}
            </>
          )}
        </p>

        <div className="trend-metrics" aria-label="Latest scan metrics">
          <div><span>Records</span><strong>{latest.recordCount.toLocaleString("en-IN")}</strong></div>
          {latestDomains.map((domain) => (
            <div key={domain}>
              <span>{DOMAIN_LABELS[domain]}</span>
              <strong>{latest[domain]}</strong>
            </div>
          ))}
        </div>

        {allPoints.length === 1 && (
          <p className="trend-note">One comparable scan is available. A second scan will establish change.</p>
        )}
        {data.skippedUnmeasuredCount > 0 && (
          <p className="trend-note">
            {data.skippedUnmeasuredCount} empty or incompatible completed scan(s) were not scored.
          </p>
        )}
      </section>
    </div>
  );
}
