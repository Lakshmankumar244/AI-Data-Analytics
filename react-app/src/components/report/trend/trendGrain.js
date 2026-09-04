export const TREND_GRAINS = [
  { id: "month", label: "Monthly" },
  { id: "week", label: "Weekly" },
  { id: "day", label: "Daily" },
  { id: "hour", label: "Hourly" },
];

function startOfGrain(date, grain) {
  const next = new Date(date);
  next.setSeconds(0, 0);
  if (grain === "hour") {
    next.setMinutes(0);
    return next;
  }
  next.setHours(0, 0, 0, 0);
  if (grain === "day") return next;
  if (grain === "week") {
    const weekday = next.getDay();
    const mondayOffset = weekday === 0 ? -6 : 1 - weekday;
    next.setDate(next.getDate() + mondayOffset);
    return next;
  }
  next.setDate(1);
  return next;
}

export function formatGrainLabel(timestamp, grain) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return String(timestamp || "Unknown");
  if (grain === "hour") {
    return new Intl.DateTimeFormat("en-IN", {
      day: "2-digit",
      month: "short",
      hour: "numeric",
    }).format(date);
  }
  if (grain === "day") {
    return new Intl.DateTimeFormat("en-IN", {
      day: "2-digit",
      month: "short",
    }).format(date);
  }
  if (grain === "week") {
    const start = startOfGrain(date, "week");
    return `Week of ${new Intl.DateTimeFormat("en-IN", {
      day: "2-digit",
      month: "short",
    }).format(start)}`;
  }
  return new Intl.DateTimeFormat("en-IN", {
    month: "short",
    year: "numeric",
  }).format(date);
}

export function bucketTrendSeries(series = [], grain = "month") {
  const buckets = new Map();
  for (const point of series) {
    const date = new Date(point.timestamp);
    if (Number.isNaN(date.getTime())) continue;
    const key = startOfGrain(date, grain).toISOString();
    const existing = buckets.get(key);
    if (!existing || date > new Date(existing.timestamp)) {
      buckets.set(key, {
        ...point,
        timestamp: startOfGrain(date, grain).toISOString(),
        period: formatGrainLabel(date, grain),
      });
    }
  }
  return Array.from(buckets.values()).sort(
    (left, right) => new Date(left.timestamp) - new Date(right.timestamp)
  );
}
