import { orgBand } from "../../../utils/bands";
import { cn } from "@/lib/utils";

export default function QualityIndicator({
  label,
  score,
  size = "md",
  emphasize = false,
}) {
  const measured = typeof score === "number";
  const band = measured ? orgBand(score) : null;
  const large = size === "lg";

  return (
    <div
      className={cn(
        "grid min-w-0 grid-cols-[minmax(0,1fr)_2.25rem] items-center gap-x-2 gap-y-1.5",
        large && "grid-cols-[minmax(0,1fr)_2.6rem]"
      )}
    >
      {label && (
        <span className="col-span-full text-[10px] font-semibold tracking-wide text-ink-muted uppercase">
          {label}
        </span>
      )}
      <div
        className={cn(
          "min-w-0 overflow-hidden rounded-full bg-surface-sunken",
          large ? "h-2" : "h-1.5"
        )}
        role="img"
        aria-label={measured ? `${score} out of 100` : "Not measured"}
      >
        {measured ? (
          <span
            className="block h-full rounded-full"
            style={{ width: `${score}%`, background: band.color }}
          />
        ) : null}
      </div>
      <span
        className={cn(
          "mono text-right font-semibold",
          large
            ? "text-base tracking-tight text-ink"
            : emphasize
              ? "text-xs text-ink"
              : "text-xs text-ink-soft"
        )}
      >
        {measured ? score : "—"}
      </span>
    </div>
  );
}
