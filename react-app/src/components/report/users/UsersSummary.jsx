import { formatNumber } from "../../../utils/format";

export default function UsersSummary({ ownerCount, recordCount, unassignedCount }) {
  return (
    <section className="users-summary" aria-label="Owner coverage">
      <div>
        <span>Owners</span>
        <strong className="mono">{formatNumber(ownerCount)}</strong>
      </div>
      <div>
        <span>Records</span>
        <strong className="mono">{formatNumber(recordCount)}</strong>
      </div>
      <div>
        <span>Unassigned</span>
        <strong className="mono">{formatNumber(unassignedCount)}</strong>
      </div>
    </section>
  );
}
