import { matrixBand } from "../../../utils/bands";
import { formatNumber } from "../../../utils/format";
import "./ModuleMatrix.css";

/**
 * D10's 20-observation floor is applied per module row here (this fixture
 * doesn't carry per-domain eligible-record counts, only a per-module total,
 * so the floor is applied at the row level as an approximation - a real
 * backend response would carry per-cell eligible counts and could apply
 * this per-cell instead).
 */
export default function ModuleMatrix({ modules, domainOrder, domainLabels, minObservations }) {
  return (
    <div className="module-matrix-wrap">
      <table className="module-matrix">
        <thead>
          <tr>
            <th className="module-matrix-rowhead">Module</th>
            <th className="module-matrix-num">Records</th>
            {domainOrder.map((d) => (
              <th key={d} className="module-matrix-num">{domainLabels[d]}</th>
            ))}
            <th className="module-matrix-num">Overall</th>
          </tr>
        </thead>
        <tbody>
          {modules.map((m) => {
            const recordCount = m.recordCount ?? 0;
            const belowFloor = recordCount < minObservations;

            return (
              <tr key={m.apiName}>
                <th scope="row" className="module-matrix-rowhead">{m.label}</th>
                <td className="module-matrix-num mono">{formatNumber(recordCount)}</td>
                {domainOrder.map((d) => {
                  const score = belowFloor ? null : m.domains[d];
                  const band = matrixBand(score);
                  return (
                    <td
                      key={d}
                      className="module-matrix-cell"
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
                  className="module-matrix-cell module-matrix-overall"
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
