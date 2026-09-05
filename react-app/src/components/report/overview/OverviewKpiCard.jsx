import { formatNumber } from "../../../utils/format";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

const ICON_TONE = {
  strong: "bg-strong-soft text-strong",
  attention: "bg-attention-soft text-attention",
  risk: "bg-risk-soft text-risk",
  flag: "bg-state-suspicious-soft text-state-suspicious",
  neutral: "bg-surface-sunken text-ink-soft",
};

const VALUE_TONE = {
  strong: "text-strong",
  attention: "text-attention",
  risk: "text-risk",
  flag: "text-state-suspicious",
  neutral: "text-ink",
};

export default function OverviewKpiCard({
  label,
  value,
  hint,
  detail,
  tone = "neutral",
  icon: Icon,
  action,
  unavailableLabel = "Not measured",
}) {
  const unavailable = value === null || value === undefined;

  return (
    <article className="flex min-w-0 flex-col gap-1.5 border-t border-line pt-3">
      <div className="flex min-w-0 items-center gap-2 text-xs font-semibold text-ink-muted">
        {Icon && (
          <span
            className={cn(
              "inline-flex size-[26px] shrink-0 items-center justify-center",
              unavailable ? "bg-surface-sunken text-ink-muted" : ICON_TONE[tone]
            )}
            aria-hidden="true"
          >
            <Icon className="size-3.5" strokeWidth={1.75} />
          </span>
        )}
        <span>{label}</span>
      </div>
      <strong
        className={cn(
          "leading-tight",
          unavailable
            ? "text-[15px] font-semibold tracking-normal text-ink-muted"
            : cn(
                "mono text-[clamp(20px,2cqi,26px)] tracking-tight",
                VALUE_TONE[tone]
              )
        )}
      >
        {unavailable ? unavailableLabel : formatNumber(value)}
      </strong>
      {detail && !unavailable && (
        <p className="text-xs font-semibold text-ink-soft">{detail}</p>
      )}
      {hint && <p className="text-xs leading-snug text-ink-muted">{hint}</p>}
      {action && (
        <Button
          type="button"
          variant="link"
          size="sm"
          className="mt-0.5 h-auto self-start px-0 print:hidden"
          onClick={action.onClick}
        >
          {action.label}
        </Button>
      )}
    </article>
  );
}
