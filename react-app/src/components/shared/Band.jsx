import "./Band.css";

/**
 * Generic label pill. Takes a resolved { id, label, color, soft } object from
 * utils/bands.js — never a raw score or hardcoded threshold. Components ask
 * bands.js for the band, then hand the result here to render it.
 */
export default function Band({ band, size = "md" }) {
  if (!band) return null;
  const style = band.soft
    ? { background: band.soft, color: band.color ?? "var(--ink)" }
    : undefined;

  return (
    <span className={`band band-${size}`} style={style}>
      {band.label}
    </span>
  );
}
