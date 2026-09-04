import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { formatDelta } from "../../../utils/format";
import "./MoversList.css";

/**
 * Biggest score changes since the prior comparable scan. Modules and users
 * are mixed in one ranked list, so each row keeps a type tag.
 */
export default function MoversList({ movers }) {
  if (!movers || movers.length === 0) {
    return <p className="movers-empty">No notable changes since your last check.</p>;
  }

  return (
    <ul className="movers-list">
      {movers.map((m) => {
        const direction = m.delta > 0 ? "up" : m.delta < 0 ? "down" : "flat";
        const Arrow =
          direction === "up" ? ArrowUpRight : direction === "down" ? ArrowDownRight : Minus;
        return (
          <li key={`${m.type}-${m.key || m.label}`} className="movers-item">
            <span className={`movers-arrow movers-arrow-${direction}`} aria-hidden="true">
              <Arrow strokeWidth={2} />
            </span>
            <span className="movers-label">{m.label}</span>
            <span className="movers-type">{m.type}</span>
            <span className={`movers-delta mono movers-delta-${direction}`}>
              {formatDelta(m.delta)}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
