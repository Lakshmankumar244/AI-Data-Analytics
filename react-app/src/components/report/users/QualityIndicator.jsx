import { orgBand } from "../../../utils/bands";
import { cn } from "@/lib/utils";

export default function QualityIndicator({
  label,
  score,
  size = "md",
  emphasize = false,
  variant = "bar",
  unavailableLabel = "n/a",
}) {
  const measured = typeof score === "number";
  const band = measured ? orgBand(score) : null;
  const large = size === "lg";
  const needsAttention = band && (band.id === "attention" || band.id === "risk");

  if (variant === "pill") {
    return (
      <span
        className={cn(
          "inline-flex min-w-[2.25rem] items-center justify-center px-1.5 py-0.5 font-semibold tracking-tight",
          measured ? "mono text-[13px]" : "text-[12px] text-ink-muted"
        )}
        style={
          measured
            ? { background: band.soft, color: needsAttention || emphasize ? band.color : "var(--ink)" }
            : { background: "var(--surface-sunken)" }
        }
      >
        {measured ? score : unavailableLabel}
      </span>
    );
  }

  return (
    <div
      className={cn(
        "grid min-w-0 grid-cols-[minmax(0,1fr)_2.25rem] items-center gap-x-2.5 gap-y-1",
        large && "grid-cols-[minmax(0,1fr)_2.75rem]"
      )}
    >
      {label && (
        <span className="eyebrow col-span-full">
          {label}
        </span>
      )}
      <div
        className={cn(
          "min-w-0 overflow-hidden bg-surface-sunken",
          large ? "h-2" : "h-1.5"
        )}
        role="img"
        aria-label={measured ? `${score} out of 100` : "Not measured"}
      >
        {measured ? (
          <span
            className="block h-full"
            style={{
              width: `${score}%`,
              background: band.color,
              opacity: needsAttention || emphasize ? 1 : 0.72,
            }}
          />
        ) : null}
      </div>
      <span
        className={cn(
          "mono text-right font-semibold tracking-tight",
          large ? "text-[17px]" : "text-[13px]",
          !measured && "text-ink-muted"
        )}
        style={
          measured && (needsAttention || emphasize)
            ? { color: band.color }
            : measured
              ? { color: "var(--ink)" }
              : undefined
        }
      >
        {measured ? score : "—"}
      </span>
    </div>
  );
}
