import { matrixBand } from "../../../utils/bands";
import { formatNumber } from "../../../utils/format";
import { cn } from "@/lib/utils";

/**
 * D10's 20-observation floor is applied per module row here (this fixture
 * doesn't carry per-domain eligible-record counts, only a per-module total,
 * so the floor is applied at the row level as an approximation - a real
 * backend response would carry per-cell eligible counts and could apply
 * this per-cell instead).
 */
export default function ModuleMatrix({ modules, domainOrder, domainLabels, minObservations }) {
  return (
    <div className="min-w-0 overflow-x-auto">
      <table className="w-full border-separate border-spacing-0 text-xs">
        <thead>
          <tr>
            <th className="border-b border-line px-2.5 py-2.5 text-left text-[9px] font-bold tracking-wide whitespace-nowrap text-ink-muted uppercase">
              Module
            </th>
            <th className="border-b border-line px-2.5 py-2.5 text-center text-[9px] font-bold tracking-wide whitespace-nowrap text-ink-muted uppercase">
              Records
            </th>
            {domainOrder.map((d) => (
              <th
                key={d}
                className="border-b border-line px-2.5 py-2.5 text-center text-[9px] font-bold tracking-wide whitespace-nowrap text-ink-muted uppercase"
              >
                {domainLabels[d]}
              </th>
            ))}
            <th className="border-b border-line px-2.5 py-2.5 text-center text-[9px] font-bold tracking-wide whitespace-nowrap text-ink-muted uppercase">
              Overall
            </th>
          </tr>
        </thead>
        <tbody className="[&>tr:last-child>th]:border-b-0 [&>tr:last-child>td]:border-b-0">
          {modules.map((m) => {
            const recordCount = m.recordCount ?? 0;
            const belowFloor = recordCount < minObservations;

            return (
              <tr key={m.apiName} className="hover:bg-surface-sunken">
                <th
                  scope="row"
                  className="border-b border-line px-2.5 py-2.5 text-left font-semibold whitespace-nowrap text-ink"
                >
                  {m.label}
                </th>
                <td className="mono border-b border-line px-2.5 py-2.5 text-center whitespace-nowrap text-ink-soft">
                  {formatNumber(recordCount)}
                </td>
                {domainOrder.map((d) => {
                  const score = belowFloor ? null : m.domains[d];
                  const band = matrixBand(score);
                  return (
                    <td
                      key={d}
                      className="border-b border-line px-2.5 py-2.5 text-center font-semibold whitespace-nowrap"
                      style={{ background: band.soft, color: band.color }}
                      title={
                        belowFloor
                          ? `Fewer than ${minObservations} records - not enough to score`
                          : score === null
                          ? "Not measured for this module"
                          : `${domainLabels[d]}: ${score}, ${band.label}`
                      }
                    >
                      {score === null ? "—" : score}
                    </td>
                  );
                })}
                <td
                  className={cn(
                    "border-b border-line px-2.5 py-2.5 text-center font-bold whitespace-nowrap",
                    belowFloor && "text-ink-soft"
                  )}
                  style={
                    belowFloor
                      ? undefined
                      : { background: matrixBand(m.overall).soft, color: matrixBand(m.overall).color }
                  }
                >
                  {belowFloor ? "—" : m.overall}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
