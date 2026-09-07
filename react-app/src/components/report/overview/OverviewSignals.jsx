import OverviewKpiCard from "./OverviewKpiCard";

function shareLabel(share) {
  if (share === null || share === undefined) return null;
  return `${share.toFixed(1)}% of period`;
}

export default function OverviewSignals({
  cleanRecords,
  attentionRecords,
  suspiciousRecords,
  cleanShare,
  attentionShare,
  usersNeedingHelp,
  onOpenUsers,
}) {
  const attentionUnavailable =
    attentionRecords === null || attentionRecords === undefined;

  return (
    <div className="grid min-h-full min-w-0 auto-rows-fr grid-cols-2 gap-3">
      <OverviewKpiCard
        label="Clean"
        value={cleanRecords}
        tone="strong"
        hint={shareLabel(cleanShare)}
      />
      <OverviewKpiCard
        label="Need attention"
        value={attentionRecords}
        tone="attention"
        hint={attentionUnavailable ? null : shareLabel(attentionShare)}
      />
      <OverviewKpiCard
        label="Look fabricated"
        value={suspiciousRecords}
        tone="flag"
      />
      <OverviewKpiCard
        label="Users needing help"
        value={usersNeedingHelp}
        tone="risk"
        action={
          onOpenUsers
            ? { label: "Open Users", onClick: onOpenUsers }
            : undefined
        }
      />
    </div>
  );
}
