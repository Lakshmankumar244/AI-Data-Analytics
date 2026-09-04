export function formatNumber(n) {
  if (n === null || n === undefined) return "\u2014";
  return new Intl.NumberFormat("en-IN").format(n);
}

function parseReportDate(value) {
  if (!value) return null;
  const normalized = String(value).replace(
    /^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})(?::\d{3})?/,
    "$1T$2"
  );
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatReportDate(value, options = {}) {
  const date = parseReportDate(value);
  if (!date) return value ? String(value) : null;
  const format = {
    day: "2-digit",
    month: "short",
  };
  if (!options.compact) format.year = "numeric";
  return new Intl.DateTimeFormat("en-IN", format).format(date);
}

export function formatReportPeriod(from, to, options = {}) {
  const startDate = parseReportDate(from);
  const endDate = parseReportDate(to);
  const sameYear =
    startDate && endDate && startDate.getFullYear() === endDate.getFullYear();
  const compact = Boolean(options.compact && sameYear);
  const start = formatReportDate(from, { compact });
  const end = formatReportDate(to, { compact });
  if (start && end) return `${start} \u2192 ${end}`;
  return start || end || null;
}

export function formatDelta(n) {
  if (n === 0) return "\u00b10";
  return n > 0 ? `+${n}` : `${n}`;
}

export function formatSeconds(s) {
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return rem ? `${m}m ${rem}s` : `${m}m`;
}
