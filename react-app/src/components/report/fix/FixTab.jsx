import { useEffect, useState } from "react";
import { useAppState } from "../../../state/AppContext";
import * as api from "../../../data/client";
import { formatNumber } from "../../../utils/format";
import LoadingState from "../../shared/LoadingState";
import { cn } from "@/lib/utils";

const PRIORITY_TONE = {
  high: "text-risk",
  medium: "text-attention",
  low: "text-ink-muted",
};

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
      <div className="flex min-w-0 flex-col py-6 pb-12 @max-[640px]:py-4 @max-[640px]:pb-8">
        <p className="text-[13px] leading-normal text-risk" role="alert">
          {error}
        </p>
      </div>
    );
  }
  if (!plan) return <LoadingState label="Loading remediation plan" />;
  if (!plan.measured) {
    return (
      <div className="flex min-w-0 flex-col py-6 pb-12 @max-[640px]:py-4 @max-[640px]:pb-8">
        <section className="min-w-0">
          <p className="eyebrow">Remediation plan</p>
          <p className="mt-2 max-w-[46ch] text-[13px] leading-normal text-ink-soft">
            Remediation recommendations were not measured in this scan. Run a new
            scan after deploying record findings.
          </p>
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
    <div className="flex min-w-0 flex-col gap-3.5 py-6 pb-12 @max-[640px]:py-4 @max-[640px]:pb-8">
      <section className="min-w-0">
        <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="eyebrow">Remediation plan</p>
            <h1 className="mt-0.5 font-heading text-xl font-semibold tracking-tight text-ink sm:text-2xl">
              What to fix, and who needs to do it
            </h1>
          </div>
          <div className="flex flex-col items-end">
            <strong className="mono text-[22px] tracking-tight text-ink">
              {formatNumber(plan.actionCount)}
            </strong>
            <span className="text-[10px] font-bold tracking-wider text-ink-muted uppercase">
              recommendations
            </span>
          </div>
        </header>

        <p className="mb-4 flex items-center gap-2.5 text-xs leading-normal text-ink-soft">
          <span
            className="grid size-6 shrink-0 place-items-center bg-brand-soft font-extrabold text-brand"
            aria-hidden="true"
          >
            ◇
          </span>
          <span>
            This connection is read-only. These are ranked recommendations for
            manual review; nothing here changes CRM records.
          </span>
        </p>

        <ul className="m-0 flex list-none flex-col p-0">
          {plan.actions.map((action) => (
            <li
              key={action.id}
              className="flex gap-3 border-t border-line py-4 first:border-t-0 first:pt-0"
            >
              <label className="mt-0.5 shrink-0">
                <input
                  type="checkbox"
                  checked={selected.has(action.id)}
                  onChange={() => toggle(action.id)}
                  className="size-[17px] accent-brand"
                />
              </label>
              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-3 @max-[640px]:flex-col @max-[640px]:items-start">
                  <h3 className="m-0 text-sm leading-snug font-bold text-ink">
                    {action.title}
                  </h3>
                  <span
                    className={cn(
                      "shrink-0 text-[10px] font-bold tracking-wide whitespace-nowrap uppercase",
                      PRIORITY_TONE[action.priority.toLowerCase()] || PRIORITY_TONE.low
                    )}
                  >
                    {action.priority} priority
                  </span>
                </div>
                <p className="mt-1.5 mb-0 max-w-[820px] text-xs leading-normal text-ink-soft">
                  {action.description}
                </p>
                <p className="mt-1.5 mb-0 text-[11px] text-ink-muted">
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
          <p className="max-w-[46ch] text-[13px] leading-normal text-ink-soft">
            No completeness or validity remediation actions were found.
          </p>
        )}
        {plan.omittedActionCount > 0 && (
          <p className="mt-3 mb-0 text-[11px] text-ink-muted">
            Showing the 30 highest-priority actions. {formatNumber(plan.omittedActionCount)} lower-priority actions are omitted.
          </p>
        )}
      </section>

      {plan.actions.length > 0 && (
        <div className="sticky bottom-0 z-10 flex items-center justify-between gap-4 border-t border-line bg-paper/95 py-3 backdrop-blur-md @max-[640px]:flex-col @max-[640px]:items-start">
          <span className="text-xs font-semibold text-ink-soft">
            {selected.size} action{selected.size === 1 ? "" : "s"} selected - {formatNumber(selectedRecords)} affected references
          </span>
          <span className="text-[11px] text-ink-muted">
            Records may overlap between actions.
          </span>
        </div>
      )}
    </div>
  );
}
