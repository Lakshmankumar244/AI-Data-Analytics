import { useEffect, useState } from "react";
import { useAppState } from "../../../state/AppContext";
import * as api from "../../../data/client";
import { formatNumber } from "../../../utils/format";
import LoadingState from "../../shared/LoadingState";
import { cn } from "@/lib/utils";

const PRIORITY_TONE = {
  high: { color: "var(--risk)", label: "High" },
  medium: { color: "var(--attention)", label: "Medium" },
  low: { color: "var(--muted)", label: "Low" },
};

function priorityMeta(priority) {
  const key = String(priority || "").toLowerCase();
  return PRIORITY_TONE[key] || PRIORITY_TONE.low;
}

function PriorityWord({ priority }) {
  const tone = priorityMeta(priority);
  return (
    <span className="inline-flex min-w-0 items-center gap-2">
      <span
        className="size-1.5 shrink-0 rounded-full"
        style={{ background: tone.color }}
        aria-hidden="true"
      />
      <span
        className="text-[13px] font-semibold tracking-tight"
        style={{ color: tone.color }}
      >
        {tone.label}
      </span>
    </span>
  );
}

function ActionFacts({ action }) {
  const facts = [
    {
      label: "Records",
      value: formatNumber(action.recordCount),
      mono: true,
    },
    action.fieldApiName
      ? { label: "Field", value: action.fieldApiName, mono: true }
      : null,
    action.modules?.length
      ? { label: "In", value: action.modules.join(", ") }
      : null,
    typeof action.coverageRate === "number"
      ? {
          label: "Coverage",
          value: `${Math.round(action.coverageRate * 100)}% of module`,
          mono: true,
        }
      : null,
  ].filter(Boolean);

  return (
    <dl className="mt-3 m-0 flex min-w-0 flex-wrap gap-x-6 gap-y-2">
      {facts.map((fact) => (
        <div key={fact.label} className="min-w-0">
          <dt className="eyebrow">{fact.label}</dt>
          <dd
            className={cn(
              "mt-0.5 mb-0 text-[13px] leading-snug text-ink",
              fact.mono && "mono font-semibold tracking-tight"
            )}
          >
            {fact.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function ActionRow({ action, checked, onToggle }) {
  const tone = priorityMeta(action.priority);

  return (
    <li
      className={cn(
        "flex gap-3 border-b border-line py-3",
        checked && "bg-surface-sunken/70"
      )}
      style={{ boxShadow: `inset 3px 0 0 ${tone.color}` }}
    >
      <label className="mt-1.5 shrink-0 pl-3 @min-[820px]:pl-3.5">
        <input
          type="checkbox"
          checked={checked}
          onChange={() => onToggle(action.id)}
          className="size-[17px] accent-brand"
          aria-label={`Select ${action.title}`}
        />
      </label>
      <div className="min-w-0 flex-1 pr-1">
        <div className="flex items-start justify-between gap-3 @max-[760px]:flex-col @max-[760px]:items-start">
          <h3 className="m-0 font-heading text-[15px] leading-snug font-semibold tracking-tight text-ink">
            {action.title}
          </h3>
          <span className="shrink-0">
            <PriorityWord priority={action.priority} />
          </span>
        </div>
        <p className="mt-1.5 mb-0 max-w-[72ch] text-[14px] leading-relaxed text-ink-soft">
          {action.description}
        </p>
        <ActionFacts action={action} />
      </div>
    </li>
  );
}

function FixEmpty({ title, children, role }) {
  return (
    <div className="flex min-w-0 flex-col py-4 pb-8 @max-[760px]:py-3 @max-[760px]:pb-6">
      <section className="min-w-0" role={role}>
        <h2 className="font-heading text-xl font-semibold tracking-tight text-ink">
          {title}
        </h2>
        <p className="mt-2 max-w-[46ch] text-sm leading-relaxed text-ink-soft">
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
    <div className="flex min-w-0 flex-col py-4 pb-8 @max-[760px]:py-3 @max-[760px]:pb-6">
      <section className="min-w-0">
        <header className="mb-5">
          <h2 className="font-heading text-xl font-semibold tracking-tight text-ink">
            Remediation plan
          </h2>
          <p className="mt-1.5 text-sm text-ink-muted">
            {formatNumber(plan.actionCount)} recommendation
            {plan.actionCount === 1 ? "" : "s"}
          </p>
        </header>

        {plan.actions.length === 0 ? (
          <p className="max-w-[46ch] text-sm leading-relaxed text-ink-soft">
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
          <p className="mt-4 mb-0 text-[13px] leading-relaxed text-ink-muted">
            Showing the 30 highest-priority actions. {formatNumber(plan.omittedActionCount)} lower-priority actions are omitted.
          </p>
        )}
      </section>

      {plan.actions.length > 0 && (
        <div className="sticky bottom-0 z-10 mt-2 flex items-center justify-between gap-4 border-t border-line bg-paper/95 py-3 backdrop-blur-md @max-[760px]:flex-col @max-[760px]:items-start">
          <span className="text-[13px] font-semibold text-ink-soft">
            {selected.size} action{selected.size === 1 ? "" : "s"} selected - {formatNumber(selectedRecords)} affected references
          </span>
          <span className="text-[12px] text-ink-muted">
            Records may overlap between actions.
          </span>
        </div>
      )}
    </div>
  );
}
