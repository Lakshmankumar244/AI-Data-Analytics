import { formatNumber } from "../../../utils/format";
import { ResponsiveGrid } from "../../layout";
import OverviewKpiCard from "../overview/OverviewKpiCard";

export default function FixKpis({ kpis }) {
  const affected = Number(kpis?.affectedRecordCount) || 0;
  const issues = Number(kpis?.issueCount) || 0;
  const fixed = 0;

  return (
    <ResponsiveGrid min="160px" gap="0.5rem" aria-label="Fix summary">
      <OverviewKpiCard
        label="Defective records"
        value={affected}
        hint="Records with at least one quality issue"
        tone="risk"
      />
      <OverviewKpiCard
        label="Issues"
        value={issues}
        hint={`${formatNumber(issues)} field-level defect${issues === 1 ? "" : "s"}`}
        tone="attention"
      />
      <OverviewKpiCard
        label="Fixed"
        value={fixed}
        hint="This app does not write back to CRM"
        tone="neutral"
      />
    </ResponsiveGrid>
  );
}
