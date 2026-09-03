import { formatNumber, formatSeconds } from "../../utils/format";

export default function CostEstimate({ estimate, loading }) {
  return (
    <div className="cost-estimate">
      <p className="eyebrow">Before you run this</p>
      {loading || !estimate ? (
        <p className="cost-estimate-loading">Calculating\u2026</p>
      ) : (
        <div className="cost-estimate-grid">
          <div>
            <span className="cost-estimate-value mono">{formatNumber(estimate.recordsInRange)}</span>
            <span className="cost-estimate-label">records in range</span>
          </div>
          <div>
            <span className="cost-estimate-value mono">{formatNumber(estimate.estimatedApiCalls)}</span>
            <span className="cost-estimate-label">API calls</span>
          </div>
          <div>
            <span className="cost-estimate-value mono">{formatSeconds(estimate.estimatedRuntimeSeconds)}</span>
            <span className="cost-estimate-label">estimated runtime</span>
          </div>
        </div>
      )}
      <p className="cost-estimate-scope">
        Read-only access. Nothing in your CRM is changed by running this scan.
      </p>
    </div>
  );
}
