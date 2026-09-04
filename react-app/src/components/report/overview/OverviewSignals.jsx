import { CircleCheck, ScanSearch, TriangleAlert, Users } from "lucide-react";
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
  suspiciousShare,
  usersNeedingHelp,
  onOpenUsers,
}) {
  return (
    <section className="overview-signals" aria-label="Attention signals">
      <OverviewKpiCard
        label="Clean records"
        value={cleanRecords}
        tone={cleanRecords === 0 ? "attention" : "strong"}
        icon={CircleCheck}
        detail={shareLabel(cleanShare)}
        hint={
          cleanRecords === null
            ? "Record-level classification is not included in the current aggregate scan."
            : "Records currently classified as proper."
        }
        unavailableLabel="Not measured"
      />
      <OverviewKpiCard
        label="Need attention"
        value={attentionRecords}
        tone="attention"
        icon={TriangleAlert}
        detail={shareLabel(attentionShare)}
        hint={
          attentionRecords === null
            ? "Record-level classification is not included in the current aggregate scan."
            : "Records in an incomplete, inaccurate, suspicious, or duplicate state."
        }
        unavailableLabel="Not measured"
      />
      <OverviewKpiCard
        label="Suspicious records"
        value={suspiciousRecords}
        tone="flag"
        icon={ScanSearch}
        detail={shareLabel(suspiciousShare)}
        hint={
          suspiciousRecords === null
            ? "Suspicious-record counts are not included in the current aggregate scan."
            : "Records classified as suspicious."
        }
        unavailableLabel="Not measured"
      />
      <OverviewKpiCard
        label="Users needing help"
        value={usersNeedingHelp}
        tone={usersNeedingHelp ? "attention" : "neutral"}
        icon={Users}
        hint={
          usersNeedingHelp === null
            ? "User-level help ranking is not available on this scan."
            : "Owners below the stable band, with enough records to score."
        }
        unavailableLabel="Not available"
        action={
          onOpenUsers
            ? { label: "Open Users", onClick: onOpenUsers }
            : undefined
        }
      />
    </section>
  );
}
