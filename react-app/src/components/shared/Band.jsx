import { cn } from "@/lib/utils";

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
    <span
      className={cn(
        "inline-flex items-center rounded-full font-semibold tracking-wide whitespace-nowrap",
        size === "lg" ? "px-3.5 py-1.5 text-[13px]" : "px-2 text-[11px]",
        size === "sm" ? "py-0.5" : size === "md" ? "py-[3px]" : ""
      )}
      style={style}
    >
      {band.label}
    </span>
  );
}
