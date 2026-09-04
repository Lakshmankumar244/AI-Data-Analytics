import ScoreBar from "../../shared/ScoreBar";
import { DOMAIN_LABELS } from "../../../utils/bands";
import { groupDomainScores } from "./overviewModel";
import "./DomainScoreBars.css";

const GROUP_META = [
  { id: "attention", label: "Needs attention" },
  { id: "healthy", label: "Healthy" },
  { id: "unavailable", label: "Not measured" },
];

export default function DomainScoreBars({ domainScores, unmeasuredDomains = [] }) {
  const groups = groupDomainScores(domainScores, unmeasuredDomains);
  const hasScores = (domainScores ?? []).length > 0;

  if (!hasScores) {
    return (
      <p className="domain-score-empty">
        Quality dimensions were not included in this scan.
      </p>
    );
  }

  return (
    <div className="domain-score-bars">
      {GROUP_META.map((group) => {
        const items = groups[group.id];
        if (!items.length) return null;
        return (
          <div key={group.id} className={`domain-score-group domain-score-group-${group.id}`}>
            <p className="eyebrow">{group.label}</p>
            {items.map((domain) => (
              <ScoreBar
                key={domain.domain}
                label={DOMAIN_LABELS[domain.domain] ?? domain.domain}
                score={domain.score}
                applicable={domain.applicable}
                reason={domain.reason}
              />
            ))}
          </div>
        );
      })}
    </div>
  );
}
