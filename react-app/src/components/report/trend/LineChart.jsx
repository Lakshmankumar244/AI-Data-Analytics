const HEIGHT = 360;
const TOP = 16;
const BOTTOM = 36;
const LEFT_PERCENT = 4.5;
const RIGHT_PERCENT = 98;

export const TREND_SERIES_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
  "var(--risk)",
];

export function trendSeriesColor(index) {
  return TREND_SERIES_COLORS[index % TREND_SERIES_COLORS.length];
}

function uniqueAxisPoints(points) {
  const seen = new Set();
  const unique = [];
  for (const point of points) {
    const time = new Date(point.timestamp).getTime();
    if (!Number.isFinite(time) || seen.has(time)) continue;
    seen.add(time);
    unique.push(point);
  }
  unique.sort((left, right) => new Date(left.timestamp) - new Date(right.timestamp));
  if (unique.length <= 8) return unique;
  const ticks = [unique[0]];
  const inner = 4;
  for (let step = 1; step <= inner; step += 1) {
    const index = Math.round((step / (inner + 1)) * (unique.length - 1));
    const candidate = unique[index];
    if (candidate !== ticks[ticks.length - 1]) ticks.push(candidate);
  }
  if (unique[unique.length - 1] !== ticks[ticks.length - 1]) {
    ticks.push(unique[unique.length - 1]);
  }
  return ticks;
}

export default function LineChart({ seriesGroups, averageScore }) {
  const groups = seriesGroups ?? [];
  const points = groups.flatMap((group) => group.series ?? []);
  const times = points.map((point) => new Date(point.timestamp).getTime()).filter(Number.isFinite);
  const minimumTime = times.length ? Math.min(...times) : 0;
  const maximumTime = times.length ? Math.max(...times) : minimumTime;
  const innerHeight = HEIGHT - TOP - BOTTOM;
  const x = (point, index, length) => {
    const timestamp = new Date(point.timestamp).getTime();
    const ratio = maximumTime > minimumTime && Number.isFinite(timestamp)
      ? (timestamp - minimumTime) / (maximumTime - minimumTime)
      : length <= 1 ? 0.5 : index / (length - 1);
    return `${LEFT_PERCENT + ratio * (RIGHT_PERCENT - LEFT_PERCENT)}%`;
  };
  const y = (score) => TOP + innerHeight * (1 - score / 100);
  const gridLines = [0, 25, 50, 75, 100];
  const orderedPoints = [...points].sort(
    (left, right) => new Date(left.timestamp) - new Date(right.timestamp)
  );
  const axisTicks = uniqueAxisPoints(orderedPoints);
  const annotateLast = groups.length === 1 && groups[0].series?.length;

  return (
    <svg
      className="block h-[360px] w-full overflow-visible"
      role="img"
      aria-label="Score over time by module"
      height={HEIGHT}
    >
      {gridLines.map((gridScore) => (
        <g key={gridScore}>
          <line
            x1={`${LEFT_PERCENT}%`}
            x2={`${RIGHT_PERCENT}%`}
            y1={y(gridScore)}
            y2={y(gridScore)}
            className={gridScore === 50 ? "stroke-line-strong" : "stroke-line"}
            strokeWidth="1"
          />
          <text
            x="3.2%"
            y={y(gridScore) + 4}
            className="mono fill-ink-muted text-[11px]"
            textAnchor="end"
          >
            {gridScore}
          </text>
        </g>
      ))}
      {typeof averageScore === "number" && (
        <g>
          <line
            x1={`${LEFT_PERCENT}%`}
            x2={`${RIGHT_PERCENT}%`}
            y1={y(averageScore)}
            y2={y(averageScore)}
            className="stroke-ink-muted"
            strokeWidth="1"
            strokeDasharray="4 4"
          />
          <text
            x={`${RIGHT_PERCENT}%`}
            y={y(averageScore) - 6}
            className="mono fill-ink-muted text-[10px]"
            textAnchor="end"
          >
            avg {averageScore.toFixed(0)}
          </text>
        </g>
      )}
      {groups.map((group, groupIndex) => {
        const color = trendSeriesColor(groupIndex);
        const label = group.label || group.moduleApiName;
        const lastPoint = group.series[group.series.length - 1];
        return (
          <g key={group.moduleApiName}>
            {group.series.slice(1).map((point, index) => {
              const previous = group.series[index];
              return (
                <line
                  key={`${previous.scanId}-${point.scanId}`}
                  x1={x(previous, index, group.series.length)}
                  x2={x(point, index + 1, group.series.length)}
                  y1={y(previous.score)}
                  y2={y(point.score)}
                  stroke={color}
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  fill="none"
                />
              );
            })}
            {group.series.map((point, index) => (
              <circle
                key={`${point.scanId}-${index}`}
                cx={x(point, index, group.series.length)}
                cy={y(point.score)}
                r="4.5"
                className="fill-surface"
                stroke={color}
                strokeWidth="2.5"
              >
                <title>{`${label}: ${point.score} - ${point.period} - ${point.recordCount.toLocaleString("en-IN")} records`}</title>
              </circle>
            ))}
            {annotateLast && lastPoint && (
              <text
                x={x(lastPoint, group.series.length - 1, group.series.length)}
                y={y(lastPoint.score) - 12}
                className="mono fill-ink text-[12px] font-semibold"
                textAnchor="middle"
              >
                {lastPoint.score}
              </text>
            )}
          </g>
        );
      })}
      {axisTicks.map((point) => (
        <text
          key={point.timestamp}
          x={x(point, 0, 1)}
          y={HEIGHT - 10}
          className="fill-ink-muted text-[11px]"
          textAnchor={
            point === axisTicks[0]
              ? "start"
              : point === axisTicks[axisTicks.length - 1]
                ? "end"
                : "middle"
          }
        >
          {point.period}
        </text>
      ))}
    </svg>
  );
}
