import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { formatDelta } from "../../../utils/format";
import "./MoversList.css";

/**
 * Biggest score changes since the prior scan, mixing module- and
 * domain-level movers (they're different kinds of things - a module is a
 * CRM object type, a domain is a quality dimension - so each gets a small
 * type tag rather than being visually conflated).
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
          <li key={`${m.type}-${m.label}`} className="movers-item">
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
