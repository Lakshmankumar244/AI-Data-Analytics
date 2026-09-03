import { RECORD_STATES } from "../../utils/bands";
import { formatNumber } from "../../utils/format";
import "./StateBreakdown.css";

/**
 * The six-state breakdown, in the fixed D3 precedence order (proper is
 * "best", confirmed_duplicate is "worst" / highest precedence). Segments are
 * clickable: clicking one sets global focusState, which the Records tab
 * (Phase 3) will use to pre-filter. Clicking the active segment clears it.
 */
export default function StateBreakdown({ breakdown, focusState, onFocus }) {
  const total = RECORD_STATES.reduce((sum, s) => sum + (breakdown[s.id] ?? 0), 0);

  return (
    <div className="state-breakdown">
      <div className="state-breakdown-bar" role="group" aria-label="Record state breakdown">
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
              className={`state-segment${isFocused ? " state-segment-focused" : ""}${isDimmed ? " state-segment-dimmed" : ""}`}
              style={{ width: `${pct}%`, background: s.color }}
              onClick={() => onFocus?.(isFocused ? null : s.id)}
              aria-pressed={isFocused}
              title={`${s.label}: ${formatNumber(count)} records (${pct.toFixed(1)}%)`}
            />
          );
        })}
      </div>

      <ul className="state-breakdown-legend">
        {RECORD_STATES.map((s) => {
          const count = breakdown[s.id] ?? 0;
          const isFocused = focusState === s.id;
          return (
            <li key={s.id}>
              <button
                type="button"
                className={`state-legend-item${isFocused ? " state-legend-item-focused" : ""}`}
                onClick={() => onFocus?.(isFocused ? null : s.id)}
                aria-pressed={isFocused}
              >
                <span className="state-legend-swatch" style={{ background: s.color }} />
                <span className="state-legend-label">{s.label}</span>
                <span className="state-legend-count mono">{formatNumber(count)}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
