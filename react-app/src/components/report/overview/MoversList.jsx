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
      <p className="py-2 text-[13px] leading-relaxed text-ink-soft">
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
            className="grid min-w-0 grid-cols-[1.75rem_minmax(0,1fr)_auto] items-center gap-x-3 border-t border-line py-2.5 first:border-t-0 first:pt-0"
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
            <span className="min-w-0">
              <span className="block truncate text-[13px] font-semibold tracking-tight text-ink">
                {m.label}
              </span>
              <span className="mt-0.5 block text-[11px] font-semibold tracking-wider text-ink-muted uppercase">
                {m.type}
              </span>
            </span>
            <span
              className={cn(
                "mono text-[16px] font-semibold tracking-tight",
                direction === "up" && "text-strong",
                direction === "down" && "text-risk",
                direction === "flat" && "text-ink-muted"
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
