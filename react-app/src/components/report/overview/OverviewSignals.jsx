import { formatNumber } from "../../../utils/format";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

function shareLabel(share) {
  if (share === null || share === undefined) return null;
  return `${share.toFixed(1)}%`;
}

function SideStat({ label, value, unavailable, action }) {
  return (
    <div className="min-w-0">
      <p className="eyebrow">{label}</p>
      <p
        className={cn(
          "mt-1 tracking-tight",
          unavailable
            ? "text-[13px] font-medium text-ink-muted"
            : "mono text-[16px] font-semibold text-ink"
        )}
      >
        {unavailable ? "Not measured" : formatNumber(value)}
      </p>
      {action && (
        <Button
          type="button"
          variant="link"
          size="sm"
          className="mt-0.5 h-auto px-0 print:hidden"
          onClick={action.onClick}
        >
          {action.label}
        </Button>
      )}
    </div>
  );
}

export default function OverviewSignals({
  cleanRecords,
  attentionRecords,
  suspiciousRecords,
  cleanShare,
  attentionShare,
  suspiciousShare,
  usersNeedingHelp,
  duplicateCount,
  onOpenUsers,
}) {
  const attentionUnavailable =
    attentionRecords === null || attentionRecords === undefined;
  const attentionTone =
    attentionUnavailable || attentionRecords === 0 ? "text-ink" : "text-attention";

  return (
    <div className="min-w-0">
      <div className="flex min-w-0 flex-wrap items-end justify-between gap-x-8 gap-y-5">
        <div className="min-w-0">
          <p
            className={cn(
              "mono font-heading text-[clamp(32px,4.2cqi,48px)] leading-none font-bold tracking-[-0.04em]",
              attentionTone
            )}
          >
            {attentionUnavailable ? "—" : formatNumber(attentionRecords)}
          </p>
          <p className="mt-2 max-w-[36ch] text-sm leading-relaxed text-ink-soft">
            {attentionUnavailable
              ? "Record-level classification is not included in the current aggregate scan."
              : `records need attention${
                  shareLabel(attentionShare) ? ` · ${shareLabel(attentionShare)} of this period` : ""
                }`}
          </p>
        </div>
        <div className="grid min-w-0 grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
          <SideStat
            label="Clean"
            value={cleanRecords}
            unavailable={cleanRecords === null}
          />
          <SideStat
            label="Duplicates"
            value={duplicateCount}
            unavailable={duplicateCount === null}
          />
          <SideStat
            label="Suspicious"
            value={suspiciousRecords}
            unavailable={suspiciousRecords === null}
          />
          <SideStat
            label="Users to help"
            value={usersNeedingHelp}
            unavailable={usersNeedingHelp === null}
            action={
              onOpenUsers
                ? { label: "Open Users", onClick: onOpenUsers }
                : undefined
            }
          />
        </div>
      </div>
      {!attentionUnavailable && shareLabel(cleanShare) && (
        <p className="mt-3 text-[13px] text-ink-muted">
          {formatNumber(cleanRecords)} records are proper
          {shareLabel(cleanShare) ? ` (${shareLabel(cleanShare)})` : ""}.
          {suspiciousRecords
            ? ` ${formatNumber(suspiciousRecords)} classified as suspicious${
                shareLabel(suspiciousShare) ? ` (${shareLabel(suspiciousShare)})` : ""
              }.`
            : ""}
        </p>
      )}
    </div>
  );
}
