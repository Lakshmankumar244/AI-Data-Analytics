import { useMemo } from "react";
import { useAppState } from "../../../state/AppContext";
import "./UsersTab.css";

const DOMAIN_WEIGHTS = { completeness: 20, validity: 15 };

function percentage(rate) {
  return typeof rate === "number" ? Math.round(rate * 100) : null;
}

function measuredScore(completeness, validity) {
  const measured = [
    [completeness, DOMAIN_WEIGHTS.completeness],
    [validity, DOMAIN_WEIGHTS.validity],
  ].filter(([score]) => score !== null);
  if (!measured.length) return null;
  return Math.round(
    measured.reduce((sum, [score, weight]) => sum + score * weight, 0) /
      measured.reduce((sum, [, weight]) => sum + weight, 0)
  );
}

function safeOwnerName(value) {
  const name = String(value || "Unassigned").trim();
  return /^\d{10,}$/.test(name) ? "Unknown owner" : name;
}

export default function UsersTab() {
  const { scan, filterModules } = useAppState();
  const owners = useMemo(() => {
    const selected = new Set(filterModules);
    const grouped = new Map();
    for (const module of scan?.moduleAnalytics ?? []) {
      if (selected.size && !selected.has(module.moduleApiName)) continue;
      for (const result of module.ownerAnalytics ?? []) {
        const data = result.data ?? {};
        if (!data.ownerKey) continue;
        const owner = grouped.get(data.ownerKey) ?? {
          ownerKey: data.ownerKey,
          ownerName: safeOwnerName(data.ownerName),
          modules: new Set(),
          recordCount: 0,
          totalCells: 0,
          populatedCells: 0,
          checkedValues: 0,
          invalidValues: 0,
        };
        owner.modules.add(module.moduleApiName);
        for (const key of [
          "recordCount",
          "totalCells",
          "populatedCells",
          "checkedValues",
          "invalidValues",
        ]) {
          owner[key] += Number(data[key]) || 0;
        }
        grouped.set(data.ownerKey, owner);
      }
    }
    return Array.from(grouped.values())
      .map((owner) => {
        const completeness = owner.totalCells
          ? percentage(owner.populatedCells / owner.totalCells)
          : null;
        const validity = owner.checkedValues
          ? percentage(
              (owner.checkedValues - owner.invalidValues) / owner.checkedValues
            )
          : null;
        return {
          ...owner,
          modules: Array.from(owner.modules).sort(),
          completeness,
          validity,
          overall: measuredScore(completeness, validity),
        };
      })
      .sort(
        (left, right) =>
          right.recordCount - left.recordCount ||
          left.ownerName.localeCompare(right.ownerName)
      );
  }, [filterModules, scan]);

  if (!owners.length) {
    return (
      <div className="users-tab">
        <section className="panel users-empty">
          <p className="eyebrow">Ownership quality</p>
          <h1>User analytics were not measured in this scan</h1>
          <p>
            Owner-level aggregates will appear for scans processed after this
            feature was deployed. Older reports remain available without them.
          </p>
        </section>
      </div>
    );
  }

  const recordCount = owners.reduce((sum, owner) => sum + owner.recordCount, 0);
  const unassignedCount = owners
    .filter((owner) => owner.ownerName === "Unassigned")
    .reduce((sum, owner) => sum + owner.recordCount, 0);

  return (
    <div className="users-tab">
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Ownership quality</p>
            <h1>Quality by CRM owner</h1>
          </div>
          <p className="users-disclosure">
            Aggregate counts only. No CRM records are displayed.
          </p>
        </div>

        <div className="users-summary">
          <div><span>Owners</span><strong>{owners.length.toLocaleString("en-IN")}</strong></div>
          <div><span>Records</span><strong>{recordCount.toLocaleString("en-IN")}</strong></div>
          <div><span>Unassigned</span><strong>{unassignedCount.toLocaleString("en-IN")}</strong></div>
        </div>

        <div className="users-table-wrap">
          <table className="users-table">
            <thead>
              <tr>
                <th>Owner</th>
                <th>Modules</th>
                <th>Records</th>
                <th>Completeness</th>
                <th>Validity</th>
                <th>Overall</th>
              </tr>
            </thead>
            <tbody>
              {owners.map((owner) => (
                <tr key={owner.ownerKey}>
                  <td>
                    <strong>{owner.ownerName}</strong>
                  </td>
                  <td>{owner.modules.join(", ")}</td>
                  <td className="mono">{owner.recordCount.toLocaleString("en-IN")}</td>
                  <td className="mono">{owner.completeness ?? "N/A"}</td>
                  <td className="mono">{owner.validity ?? "N/A"}</td>
                  <td className="mono users-overall">{owner.overall ?? "N/A"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
