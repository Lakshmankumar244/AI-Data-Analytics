import ScoreGauge from "../../shared/ScoreGauge";
import { formatNumber } from "../../../utils/format";
import { orgBand } from "../../../utils/bands";

function HeroFact({ label, children }) {
  return (
    <div className="min-w-0">
      <dt className="eyebrow">{label}</dt>
      <dd className="mono mt-1 text-[15px] font-semibold tracking-tight text-ink">
        {children}
      </dd>
    </div>
  );
}

export default function OverviewHealthHero({
  overallScore,
  priorScore,
  measuredPoints,
  possiblePoints,
  unmeasuredDomains,
  explanation,
  reuseNotice,
  recordsInScope,
  moduleCount,
  duplicateCount,
}) {
  const band = orgBand(overallScore);

  return (
    <section
      className="flex h-full min-w-0 flex-col rounded-md border border-line bg-surface p-6 @min-[640px]:p-7"
      style={{ boxShadow: `inset 3px 0 0 ${band.color}` }}
    >
      {reuseNotice && (
        <div
          className="mb-5 border-l-2 border-brand py-2 pl-3 text-[13px] leading-snug text-brand-strong"
          role="status"
        >
          {reuseNotice}
        </div>
      )}
      <h2 className="font-heading text-xl font-semibold tracking-tight text-ink">
        Overall health
      </h2>
      <div className="mt-4">
        <ScoreGauge
          score={overallScore}
          priorScore={priorScore}
          measuredPoints={measuredPoints}
          possiblePoints={possiblePoints}
          unmeasuredDomains={unmeasuredDomains}
        />
      </div>
      {explanation && (
        <p className="mt-5 max-w-[44ch] text-sm leading-relaxed text-ink-soft">
          {explanation}
        </p>
      )}
      <dl className="mt-auto grid grid-cols-3 gap-x-8 gap-y-3 border-t border-line pt-4">
        <HeroFact label="Checked">
          {formatNumber(recordsInScope)}
        </HeroFact>
        <HeroFact label="Duplicates">
          {formatNumber(duplicateCount)}
        </HeroFact>
        <HeroFact label="Modules">
          {formatNumber(moduleCount)}
        </HeroFact>
      </dl>
    </section>
  );
}
