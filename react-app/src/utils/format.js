export function formatNumber(n) {
  if (n === null || n === undefined) return "\u2014";
  return new Intl.NumberFormat("en-IN").format(n);
}

export function parseCatalystDate(value) {
  if (value == null || value === "") return null;
  if (typeof value === "number" && Number.isFinite(value)) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
  }
  const raw = String(value).trim();
  const match = raw.match(
    /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})(?:[:.](\d{1,6}))?(?:Z|[+-]\d{2}:?\d{2})?$/
  );
  if (match) {
    const [, year, month, day, hour, minute, second, fraction] = match;
    const ms = fraction ? Number(String(fraction).padEnd(3, "0").slice(0, 3)) : 0;
    if (/Z|[+-]\d{2}:?\d{2}$/.test(raw)) {
      const iso = raw.includes("T")
        ? raw
        : raw.replace(" ", "T").replace(/:(\d{3,6})(Z|[+-])/, ".$1$2");
      const date = new Date(iso);
      return Number.isNaN(date.getTime()) ? null : date;
    }
    return new Date(
      Number(year),
      Number(month) - 1,
      Number(day),
      Number(hour),
      Number(minute),
      Number(second),
      ms
    );
  }
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatScanTimestamp(value) {
  const date = parseCatalystDate(value);
  if (!date) return "\u2014";
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
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
