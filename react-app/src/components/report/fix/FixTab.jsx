import { useEffect, useState } from "react";
import { useAppState } from "../../../state/AppContext";
import * as api from "../../../data/client";
import { formatNumber } from "../../../utils/format";
import LoadingState from "../../shared/LoadingState";
import { cn } from "@/lib/utils";

const PRIORITY_TONE = {
  high: {
    color: "var(--risk)",
    background: "var(--risk-soft)",
    label: "High",
  },
  medium: {
    color: "var(--attention)",
    background: "var(--attention-soft)",
    label: "Medium",
  },
  low: {
    color: "var(--muted)",
    background: "var(--surface-sunken)",
    label: "Low",
  },
};

function priorityMeta(priority) {
  const key = String(priority || "").toLowerCase();
  return PRIORITY_TONE[key] || PRIORITY_TONE.low;
}

function PriorityBadge({ priority }) {
  const tone = priorityMeta(priority);
  return (
    <span
      className="inline-flex shrink-0 px-1.5 py-0.5 text-[10px] font-semibold tracking-wider uppercase"
      style={{ background: tone.background, color: tone.color }}
    >
      {tone.label}
    </span>
  );
}

function ActionMeta({ action }) {
  const facts = [
    {
      key: "records",
      node: (
        <>
          <strong className="mono font-semibold tracking-tight text-ink">
            {formatNumber(action.recordCount)}
          </strong>{" "}
          record{action.recordCount === 1 ? "" : "s"}
        </>
      ),
    },
    action.fieldApiName
      ? {
          key: "field",
          node: (
            <>
              Field{" "}
              <span className="mono text-ink">{action.fieldApiName}</span>
            </>
          ),
        }
      : null,
    action.modules?.length
      ? {
          key: "module",
          node: action.modules.join(", "),
        }
      : null,
    typeof action.coverageRate === "number"
      ? {
          key: "coverage",
          node: (
            <>
              Coverage{" "}
              <span className="mono text-ink">
                {Math.round(action.coverageRate * 100)}%
              </span>{" "}
              of module
            </>
          ),
        }
      : null,
  ].filter(Boolean);

  if (facts.length === 0) return null;

  return (
    <p className="mt-1.5 mb-0 flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-0.5 text-[12px] leading-snug text-ink-muted">
      {facts.map((fact, index) => (
        <span key={fact.key} className="inline-flex min-w-0 items-baseline gap-x-3">
          {index > 0 && (
            <span className="text-line-strong" aria-hidden="true">
              ·
            </span>
          )}
          <span className="min-w-0 [overflow-wrap:anywhere]">{fact.node}</span>
        </span>
      ))}
    </p>
  );
}

function ActionRow({ action, checked, onToggle }) {
  const tone = priorityMeta(action.priority);

  return (
    <li
      className={cn(
        "flex gap-3 border-b border-line py-2.5 last:border-b-0",
        checked && "bg-surface-sunken/70"
      )}
      style={{ boxShadow: `inset 3px 0 0 ${tone.color}` }}
    >
      <label className="mt-0.5 shrink-0 pl-4 @min-[640px]:pl-5">
        <input
          type="checkbox"
          checked={checked}
          onChange={() => onToggle(action.id)}
          className="size-[17px] accent-brand"
          aria-label={`Select ${action.title}`}
        />
      </label>
      <div className="min-w-0 flex-1 py-0.5 pr-4 @min-[640px]:pr-5">
        <div className="flex items-start justify-between gap-3">
          <h3 className="m-0 font-heading text-[15px] leading-snug font-semibold tracking-tight text-ink">
            {action.title}
          </h3>
          <PriorityBadge priority={action.priority} />
        </div>
        {action.description && (
          <p className="mt-1 mb-0 max-w-[72ch] text-[13px] leading-snug text-ink-soft">
            {action.description}
          </p>
        )}
        <ActionMeta action={action} />
      </div>
    </li>
  );
}

function FixEmpty({ title, children, role }) {
  return (
    <div className="flex min-w-0 flex-col py-4 pb-8 @max-[760px]:py-3 @max-[760px]:pb-6">
      <section className="min-w-0 rounded-md border border-line bg-surface p-5 @min-[640px]:p-6">
        <h2 className="font-heading text-xl font-semibold tracking-tight text-ink">
          {title}
        </h2>
        <p className="mt-2 mb-0 max-w-[46ch] text-sm leading-relaxed text-ink-soft" role={role}>
          {children}
        </p>
      </section>
    </div>
  );
}

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
      <div className="flex min-w-0 flex-col py-4 pb-8 @max-[760px]:py-3 @max-[760px]:pb-6">
        <p className="text-[13px] leading-normal text-risk" role="alert">
          {error}
        </p>
      </div>
    );
  }
  if (!plan) return <LoadingState label="Loading remediation plan" />;
  if (!plan.measured) {
    return (
      <FixEmpty title="Remediation was not measured">
        Run a new scan after deploying record findings.
      </FixEmpty>
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
    <div className="flex min-w-0 flex-col gap-3 py-4 pb-8 @max-[760px]:py-3 @max-[760px]:pb-6">
      <section className="flex min-w-0 flex-col overflow-hidden rounded-md border border-line bg-surface">
        <header className="border-b border-line px-4 py-4 @min-[640px]:px-5">
          <h2 className="font-heading text-xl font-semibold tracking-tight text-ink">
            Remediation plan
          </h2>
          <p className="mt-1 mb-0 text-sm text-ink-muted">
            {formatNumber(plan.actionCount)} recommendation
            {plan.actionCount === 1 ? "" : "s"}
          </p>
        </header>

        {plan.actions.length === 0 ? (
          <p className="m-0 max-w-[46ch] px-4 py-6 text-sm leading-relaxed text-ink-soft @min-[640px]:px-5">
            No completeness or validity actions were found.
          </p>
        ) : (
          <ul className="m-0 list-none p-0">
            {plan.actions.map((action) => (
              <ActionRow
                key={action.id}
                action={action}
                checked={selected.has(action.id)}
                onToggle={toggle}
              />
            ))}
          </ul>
        )}

        {plan.omittedActionCount > 0 && (
          <p className="m-0 border-t border-line px-4 py-3 text-[13px] leading-relaxed text-ink-muted @min-[640px]:px-5">
            Showing the 30 highest-priority actions. {formatNumber(plan.omittedActionCount)} lower-priority actions are omitted.
          </p>
        )}
      </section>

      {plan.actions.length > 0 && (
        <div className="sticky bottom-0 z-10 flex items-center justify-between gap-x-4 gap-y-1 rounded-md border border-line bg-surface px-4 py-3 @max-[760px]:flex-col @max-[760px]:items-start @min-[640px]:px-5">
          <p className="m-0 flex min-w-0 flex-wrap items-baseline gap-x-2.5 text-[13px] font-semibold text-ink">
            <span>
              {selected.size} action{selected.size === 1 ? "" : "s"} selected
            </span>
            <span className="font-normal text-line-strong" aria-hidden="true">
              |
            </span>
            <span>
              {formatNumber(selectedRecords)} record
              {selectedRecords === 1 ? "" : "s"}
            </span>
          </p>
          <p className="m-0 text-[12px] text-ink-muted">
            Records may overlap between actions.
          </p>
        </div>
      )}
    </div>
  );
}
