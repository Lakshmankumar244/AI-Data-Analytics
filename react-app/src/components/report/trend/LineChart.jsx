const HEIGHT = 220;
const TOP = 16;
const BOTTOM = 30;
const LEFT_PERCENT = 4;
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
  const firstPeriod = orderedPoints[0]?.period;
  const lastPeriod = orderedPoints[orderedPoints.length - 1]?.period;

  return (
    <svg
      className="mt-1 block h-[220px] w-full overflow-hidden"
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
            className="stroke-line"
            strokeWidth="1"
          />
          <text
            x="3%"
            y={y(gridScore) + 4}
            className="mono fill-ink-muted text-[9px]"
            textAnchor="end"
          >
            {gridScore}
          </text>
        </g>
      ))}
      {typeof averageScore === "number" && (
        <line
          x1={`${LEFT_PERCENT}%`}
          x2={`${RIGHT_PERCENT}%`}
          y1={y(averageScore)}
          y2={y(averageScore)}
          className="stroke-line-strong"
          strokeWidth="1"
          strokeDasharray="4 4"
        />
      )}
      {groups.map((group, groupIndex) => {
        const color = trendSeriesColor(groupIndex);
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
                r="4"
                className="fill-surface"
                stroke={color}
                strokeWidth="2.5"
              >
                <title>{`${group.moduleApiName}: ${point.score} - ${point.period} - ${point.recordCount.toLocaleString("en-IN")} records`}</title>
              </circle>
            ))}
          </g>
        );
      })}
      {firstPeriod && (
        <text
          x={`${LEFT_PERCENT}%`}
          y={HEIGHT - 7}
          className="fill-ink-muted text-[9px]"
          textAnchor="start"
        >
          {firstPeriod}
        </text>
      )}
      {lastPeriod && lastPeriod !== firstPeriod && (
        <text
          x={`${RIGHT_PERCENT}%`}
          y={HEIGHT - 7}
          className="fill-ink-muted text-[9px]"
          textAnchor="end"
        >
          {lastPeriod}
        </text>
      )}
    </svg>
  );
}
