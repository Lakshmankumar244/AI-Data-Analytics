import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { formatDelta } from "../../../utils/format";
import { cn } from "@/lib/utils";

/**
 * Biggest score changes since the prior comparable scan. Modules and users
 * are mixed in one ranked list, so each row keeps a type tag.
 */
export default function MoversList({ movers }) {
  if (!movers || movers.length === 0) {
    return (
      <p className="flex h-full min-h-[120px] items-center bg-surface-sunken px-4 py-3 text-[13px] leading-normal text-ink-soft">
        No notable changes since your last check.
      </p>
    );
  }

  return (
    <ul className="m-0 flex list-none flex-col p-0">
      {movers.map((m) => {
        const direction = m.delta > 0 ? "up" : m.delta < 0 ? "down" : "flat";
        const Arrow =
          direction === "up" ? ArrowUpRight : direction === "down" ? ArrowDownRight : Minus;
        return (
          <li
            key={`${m.type}-${m.key || m.label}`}
            className="grid min-w-0 grid-cols-[28px_minmax(0,1fr)_auto_auto] items-center gap-3 border-t border-line py-3 first:border-t-0 @max-[420px]:grid-cols-[28px_minmax(0,1fr)_auto]"
          >
            <span
              className={cn(
                "inline-flex size-7 items-center justify-center",
                direction === "up" && "bg-strong-soft text-strong",
                direction === "down" && "bg-risk-soft text-risk",
                direction === "flat" && "bg-surface-sunken text-ink-muted"
              )}
              aria-hidden="true"
            >
              <Arrow className="size-3.5" strokeWidth={2} />
            </span>
            <span className="min-w-0 truncate text-[13px] font-semibold text-ink">
              {m.label}
            </span>
            <span className="bg-surface-sunken px-2 py-0.5 text-[10px] font-bold tracking-wider text-ink-muted uppercase @max-[420px]:col-start-2 @max-[420px]:row-start-2 @max-[420px]:justify-self-start">
              {m.type}
            </span>
            <span
              className={cn(
                "mono min-w-[34px] text-right text-[13px] font-semibold",
                direction === "up" && "text-strong",
                direction === "down" && "text-risk",
                "@max-[420px]:col-start-3 @max-[420px]:row-span-2"
              )}
            >
              {formatDelta(m.delta)}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
