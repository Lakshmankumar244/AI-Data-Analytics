export function formatNumber(n) {
  if (n === null || n === undefined) return "\u2014";
  return new Intl.NumberFormat("en-IN").format(n);
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
