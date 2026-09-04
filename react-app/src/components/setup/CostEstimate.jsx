import { formatNumber, formatSeconds } from "../../utils/format";

export default function CostEstimate({ estimate, loading }) {
  if (loading || !estimate) {
    return <span className="cost-estimate-loading">Calculating{"\u2026"}</span>;
  }

  return (
    <>
      <span>
        {formatNumber(estimate.recordsInRange)} records in range
      </span>
      <span className="setup-summary-sep" aria-hidden="true">
        |
      </span>
      <span>
        {formatNumber(estimate.estimatedApiCalls)} API calls
      </span>
      <span className="setup-summary-sep" aria-hidden="true">
        |
      </span>
      <span>
        {formatSeconds(estimate.estimatedRuntimeSeconds)} estimated runtime
      </span>
    </>
  );
}
