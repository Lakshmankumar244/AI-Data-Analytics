import { RECORD_STATES } from "../../utils/bands";
import { formatNumber } from "../../utils/format";
import { cn } from "@/lib/utils";

/**
 * Six-state record mix, in D3 precedence order. The bar is the mix at a
 * glance; the list is the story of where volume sits. Clicking a state sets
 * global focus for the Records tab.
 */
export default function StateBreakdown({ breakdown, focusState, onFocus }) {
  const total = RECORD_STATES.reduce((sum, s) => sum + (breakdown[s.id] ?? 0), 0);

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div
        className="flex h-9 overflow-hidden bg-surface-sunken"
        role="group"
        aria-label="Record state breakdown"
      >
        {RECORD_STATES.map((s) => {
          const count = breakdown[s.id] ?? 0;
          if (count === 0) return null;
          const pct = total > 0 ? (count / total) * 100 : 0;
          const isFocused = focusState === s.id;
          const isDimmed = focusState && focusState !== s.id;
          return (
            <button
              key={s.id}
              type="button"
              className={cn(
                "m-0 h-full min-w-[4px] cursor-pointer border-0 p-0 transition-[opacity,filter] duration-150 hover:brightness-90",
                isFocused && "outline-2 outline-offset-[-2px] outline-ink",
                isDimmed && "opacity-35"
              )}
              style={{ width: `${pct}%`, background: s.color }}
              onClick={() => onFocus?.(isFocused ? null : s.id)}
              aria-pressed={isFocused}
              title={`${s.label}: ${formatNumber(count)} records (${pct.toFixed(1)}%)`}
            />
          );
        })}
      </div>

      <ul className="m-0 grid list-none grid-cols-1 gap-x-6 gap-y-0.5 p-0 sm:grid-cols-2">
        {RECORD_STATES.map((s) => {
          const count = breakdown[s.id] ?? 0;
          const isFocused = focusState === s.id;
          const share = total > 0 ? (count / total) * 100 : 0;
          const empty = count === 0;
          return (
            <li key={s.id}>
              <button
                type="button"
                className={cn(
                  "flex w-full min-w-0 items-center gap-2.5 px-1.5 py-1.5 text-left",
                  empty ? "text-ink-muted" : "text-ink-soft hover:bg-surface-sunken hover:text-ink",
                  isFocused && "bg-surface-sunken text-ink"
                )}
                onClick={() => onFocus?.(isFocused ? null : s.id)}
                aria-pressed={isFocused}
              >
                <span
                  className="size-2 shrink-0 rounded-full"
                  style={{ background: s.color, opacity: empty ? 0.35 : 1 }}
                />
                <span
                  className={cn(
                    "min-w-0 flex-1 truncate text-[13px]",
                    isFocused && "font-semibold text-ink"
                  )}
                >
                  {s.label}
                </span>
                <span
                  className={cn(
                    "mono text-[13px] font-semibold tracking-tight",
                    empty ? "text-ink-muted" : "text-ink"
                  )}
                >
                  {formatNumber(count)}
                </span>
                <span className="mono w-[3.75em] text-right text-[11px] text-ink-muted">
                  {total > 0 ? `${share.toFixed(1)}%` : "—"}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
