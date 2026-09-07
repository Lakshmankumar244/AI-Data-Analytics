import ScoreBar from "../../shared/ScoreBar";
import { DOMAIN_LABELS } from "../../../utils/bands";
import { groupDomainScores } from "./overviewModel";

const GROUP_ORDER = ["attention", "healthy", "unavailable"];

export default function DomainScoreBars({ domainScores, unmeasuredDomains = [] }) {
  const groups = groupDomainScores(domainScores, unmeasuredDomains);
  const hasScores = (domainScores ?? []).length > 0;
  const items = GROUP_ORDER.flatMap((id) => groups[id] ?? []);

  if (!hasScores) {
    return (
      <p className="text-[13px] leading-normal text-ink-soft">
        Quality dimensions were not included in this scan.
      </p>
    );
  }

  return (
    <div className="grid min-w-0 grid-cols-1 @min-[480px]:grid-cols-2 @min-[480px]:gap-x-8">
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
}
