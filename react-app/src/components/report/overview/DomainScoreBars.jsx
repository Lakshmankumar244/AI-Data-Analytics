import ScoreBar from "../../shared/ScoreBar";
import { DOMAIN_LABELS } from "../../../utils/bands";
import { groupDomainScores } from "./overviewModel";
import { cn } from "@/lib/utils";

const GROUP_META = [
  { id: "attention", label: "Needs attention", eyebrow: "text-attention" },
  { id: "healthy", label: "Healthy", eyebrow: "text-stable" },
  { id: "unavailable", label: "Not measured", eyebrow: "text-ink-muted" },
];

export default function DomainScoreBars({ domainScores, unmeasuredDomains = [] }) {
  const groups = groupDomainScores(domainScores, unmeasuredDomains);
  const hasScores = (domainScores ?? []).length > 0;

  if (!hasScores) {
    return (
      <p className="text-[13px] leading-normal text-ink-soft">
        Quality dimensions were not included in this scan.
      </p>
    );
  }

  return (
    <div className="flex min-w-0 flex-col gap-5">
      {GROUP_META.map((group) => {
        const items = groups[group.id];
        if (!items.length) return null;
        return (
          <div key={group.id}>
            <p className={cn("eyebrow mb-0.5", group.eyebrow)}>{group.label}</p>
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
