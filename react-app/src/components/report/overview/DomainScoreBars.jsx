import ScoreBar from "../../shared/ScoreBar";
import { DOMAIN_LABELS } from "../../../utils/bands";
import "./DomainScoreBars.css";

export default function DomainScoreBars({ domainScores, unmeasuredDomains = [] }) {
  const reasonFor = (domainId) =>
    unmeasuredDomains.find((u) => u.domain === domainId)?.reason;

  return (
    <div className="domain-score-bars">
      {domainScores.filter((domain) => domain.applicable).map((d) => (
        <ScoreBar
          key={d.domain}
          label={DOMAIN_LABELS[d.domain] ?? d.domain}
          score={d.score}
          applicable={d.applicable}
          reason={d.applicable ? undefined : reasonFor(d.domain)}
        />
      ))}
      {unmeasuredDomains.length > 0 && (
        <div className="domain-score-coverage">
          <strong>{domainScores.length - unmeasuredDomains.length} of {domainScores.length} measured</strong>
          <span>
            {unmeasuredDomains.map((domain) => DOMAIN_LABELS[domain.domain] ?? domain.domain).join(", ")}
            {" "}were not applicable or are not supported by the current pipeline.
          </span>
        </div>
      )}
    </div>
  );
}
