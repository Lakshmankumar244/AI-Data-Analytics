import { RECORD_STATES } from "../../utils/bands";
import { formatNumber } from "../../utils/format";
import { cn } from "@/lib/utils";

/**
 * The six-state breakdown, in the fixed D3 precedence order (proper is
 * "best", confirmed_duplicate is "worst" / highest precedence). Segments are
 * clickable: clicking one sets global focusState, which the Records tab
 * (Phase 3) will use to pre-filter. Clicking the active segment clears it.
 */
export default function StateBreakdown({ breakdown, focusState, onFocus }) {
  const total = RECORD_STATES.reduce((sum, s) => sum + (breakdown[s.id] ?? 0), 0);

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div
        className="flex h-3.5 overflow-hidden rounded-full border border-line bg-surface-sunken"
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
                "m-0 h-full min-w-[3px] cursor-pointer border-0 p-0 transition-[opacity,filter] duration-150 hover:brightness-90",
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

      <ul className="m-0 grid list-none grid-cols-[repeat(auto-fit,minmax(min(188px,100%),1fr))] gap-2 p-0">
        {RECORD_STATES.map((s) => {
          const count = breakdown[s.id] ?? 0;
          const isFocused = focusState === s.id;
          return (
            <li key={s.id}>
              <button
                type="button"
                className={cn(
                  "flex w-full min-w-0 items-center gap-2 border border-transparent bg-surface-sunken px-2.5 py-2 text-left text-[13px] text-ink-soft hover:border-line-strong",
                  isFocused && "border-line-strong bg-surface text-ink shadow-[var(--shadow-card)]"
                )}
                onClick={() => onFocus?.(isFocused ? null : s.id)}
                aria-pressed={isFocused}
              >
                <span
                  className="size-2 shrink-0 rounded-full"
                  style={{ background: s.color }}
                />
                <span className="min-w-0 flex-1 truncate">{s.label}</span>
                <span className="mono text-xs font-semibold text-ink">
                  {formatNumber(count)}
                </span>
                <span className="mono min-w-[3.25em] text-right text-[11px] font-medium text-ink-muted">
                  {total > 0 ? `${((count / total) * 100).toFixed(1)}%` : "—"}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
