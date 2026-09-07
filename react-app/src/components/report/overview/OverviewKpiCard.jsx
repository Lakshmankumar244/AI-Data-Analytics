import { formatNumber } from "../../../utils/format";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

const TILE = {
  strong: "bg-strong-soft",
  attention: "bg-attention-soft",
  risk: "bg-risk-soft",
  flag: "bg-state-suspicious-soft",
  neutral: "bg-surface-sunken",
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
  action,
  unavailableLabel = "Not measured",
}) {
  const unavailable = value === null || value === undefined;

  return (
    <article
      className={cn(
        "flex h-full min-w-0 flex-col gap-1 rounded-md px-4 py-4",
        unavailable ? "bg-surface-sunken" : TILE[tone]
      )}
    >
      <p className="eyebrow text-ink-muted">{label}</p>
      <strong
        className={cn(
          "leading-tight",
          unavailable
            ? "text-[15px] font-semibold tracking-normal text-ink-muted"
            : cn("mono text-[clamp(22px,2.6cqi,30px)] tracking-tight", VALUE_TONE[tone])
        )}
      >
        {unavailable ? unavailableLabel : formatNumber(value)}
      </strong>
      {detail && !unavailable && (
        <p className="text-xs font-semibold text-ink-soft">{detail}</p>
      )}
      {hint && !unavailable && (
        <p className="text-xs leading-snug text-ink-muted">{hint}</p>
      )}
      {action && (
        <Button
          type="button"
          variant="link"
          size="sm"
          className="mt-auto h-auto self-start px-0 print:hidden"
          onClick={action.onClick}
        >
          {action.label}
        </Button>
      )}
    </article>
  );
}
