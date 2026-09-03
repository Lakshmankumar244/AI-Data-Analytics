import { useEffect, useState } from "react";
import { useAppState } from "../../../state/AppContext";
import * as api from "../../../data/client";
import { formatNumber } from "../../../utils/format";
import LoadingState from "../../shared/LoadingState";
import "./FixTab.css";

export default function FixTab() {
  const { scanId, filterModules } = useAppState();
  const [plan, setPlan] = useState(null);
  const [selected, setSelected] = useState(() => new Set());
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setPlan(null);
    setError(null);
    setSelected(new Set());
    api.getFixPlan(scanId, filterModules)
      .then((nextPlan) => {
        if (!cancelled) setPlan(nextPlan);
      })
      .catch((requestError) => {
        if (!cancelled) setError(requestError.message);
      });
    return () => {
      cancelled = true;
    };
  }, [scanId, filterModules]);

  if (error) {
    return (
      <div className="fix-tab">
        <div className="fix-message fix-error">{error}</div>
      </div>
    );
  }
  if (!plan) return <LoadingState label="Loading remediation plan" />;
  if (!plan.measured) {
    return (
      <div className="fix-tab">
        <section className="panel fix-message">
          Remediation recommendations were not measured in this scan. Run a new
          scan after deploying record findings.
        </section>
      </div>
    );
  }

  function toggle(id) {
    setSelected((previous) => {
      const next = new Set(previous);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  const selectedActions = plan.actions.filter((action) => selected.has(action.id));
  const selectedRecords = selectedActions.reduce(
    (sum, action) => sum + action.recordCount,
    0
  );

  return (
    <div className="fix-tab">
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Remediation plan</p>
            <h1>What to fix, and who needs to do it</h1>
          </div>
          <div className="fix-header-count">
            <strong>{formatNumber(plan.actionCount)}</strong>
            <span>recommendations</span>
          </div>
        </div>

        <p className="fix-readonly-note">
          <span className="fix-readonly-icon" aria-hidden="true">◇</span>
          <span>
          This connection is read-only. These are ranked recommendations for
          manual review; nothing here changes CRM records.
          </span>
        </p>

        <ul className="fix-action-list">
          {plan.actions.map((action) => (
            <li key={action.id} className="fix-action">
              <label className="fix-action-check">
                <input
                  type="checkbox"
                  checked={selected.has(action.id)}
                  onChange={() => toggle(action.id)}
                />
              </label>
              <div className="fix-action-body">
                <div className="fix-action-top">
                  <h3>{action.title}</h3>
                  <span
                    className={`fix-priority fix-priority-${action.priority.toLowerCase()}`}
                  >
                    {action.priority} priority
                  </span>
                </div>
                <p className="fix-action-desc">{action.description}</p>
                <p className="fix-action-meta">
                  <span className="mono">{formatNumber(action.recordCount)}</span>
                  {" records - "}{action.modules.join(", ")}{" - "}{action.fieldApiName}
                  {typeof action.coverageRate === "number"
                    ? ` - ${Math.round(action.coverageRate * 100)}% of module`
                    : ""}
                </p>
              </div>
            </li>
          ))}
        </ul>

        {plan.actions.length === 0 && (
          <div className="fix-message">
            No completeness or validity remediation actions were found.
          </div>
        )}
        {plan.omittedActionCount > 0 && (
          <p className="fix-omitted">
            Showing the 30 highest-priority actions. {formatNumber(plan.omittedActionCount)} lower-priority actions are omitted.
          </p>
        )}
      </section>

      {plan.actions.length > 0 && (
        <div className="fix-summary-bar">
          <span className="fix-summary-detail">
            {selected.size} action{selected.size === 1 ? "" : "s"} selected - {formatNumber(selectedRecords)} affected references
          </span>
          <span className="fix-summary-overlap">
            Records may overlap between actions.
          </span>
        </div>
      )}
    </div>
  );
}
