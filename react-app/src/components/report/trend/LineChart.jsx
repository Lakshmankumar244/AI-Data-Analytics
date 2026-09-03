import "./LineChart.css";

const HEIGHT = 220;
const TOP = 16;
const BOTTOM = 30;
const LEFT_PERCENT = 4;
const RIGHT_PERCENT = 98;

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
    <svg className="line-chart" role="img" aria-label="Score over time by module" height={HEIGHT}>
      {gridLines.map((gridScore) => (
        <g key={gridScore}>
          <line x1={`${LEFT_PERCENT}%`} x2={`${RIGHT_PERCENT}%`} y1={y(gridScore)} y2={y(gridScore)} className="line-chart-grid" />
          <text x="3%" y={y(gridScore) + 4} className="line-chart-axis-label mono" textAnchor="end">{gridScore}</text>
        </g>
      ))}
      {typeof averageScore === "number" && (
        <line x1={`${LEFT_PERCENT}%`} x2={`${RIGHT_PERCENT}%`} y1={y(averageScore)} y2={y(averageScore)} className="line-chart-average" />
      )}
      {groups.map((group, groupIndex) => (
        <g key={group.moduleApiName} className={`line-chart-series line-chart-series-${groupIndex % 6}`}>
          {group.series.slice(1).map((point, index) => {
            const previous = group.series[index];
            return (
              <line key={`${previous.scanId}-${point.scanId}`} x1={x(previous, index, group.series.length)} x2={x(point, index + 1, group.series.length)} y1={y(previous.score)} y2={y(point.score)} className="line-chart-line" />
            );
          })}
          {group.series.map((point, index) => (
            <circle key={`${point.scanId}-${index}`} cx={x(point, index, group.series.length)} cy={y(point.score)} r="4" className="line-chart-point">
              <title>{`${group.moduleApiName}: ${point.score} - ${point.period} - ${point.recordCount.toLocaleString("en-IN")} records`}</title>
            </circle>
          ))}
        </g>
      ))}
      {firstPeriod && <text x={`${LEFT_PERCENT}%`} y={HEIGHT - 7} className="line-chart-axis-label" textAnchor="start">{firstPeriod}</text>}
      {lastPeriod && lastPeriod !== firstPeriod && <text x={`${RIGHT_PERCENT}%`} y={HEIGHT - 7} className="line-chart-axis-label" textAnchor="end">{lastPeriod}</text>}
    </svg>
  );
}
