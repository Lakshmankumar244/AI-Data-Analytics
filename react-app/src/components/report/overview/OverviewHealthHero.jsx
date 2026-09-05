import ScoreGauge from "../../shared/ScoreGauge";

export default function OverviewHealthHero({
  overallScore,
  priorScore,
  measuredPoints,
  possiblePoints,
  unmeasuredDomains,
  explanation,
  reuseNotice,
}) {
  return (
    <section className="flex min-w-0 flex-col">
      {reuseNotice && (
        <div
          className="mb-4 border-b border-brand/30 bg-brand-soft px-0 py-3 text-[13px] leading-snug text-brand-strong"
          role="status"
        >
          {reuseNotice}
        </div>
      )}
      <p className="eyebrow">Overall health</p>
      <h2 className="sr-only">Overall health</h2>
      <div className="mt-3 min-w-0 [&_.score-gauge]:gap-[clamp(16px,3cqi,32px)] [&_.score-gauge-number]:text-[clamp(34px,4.4cqi,44px)] [&_.score-gauge-ring-wrap]:w-[min(132px,100%)] [&_.score-gauge-ring-wrap]:basis-[132px]">
        <ScoreGauge
          score={overallScore}
          priorScore={priorScore}
          measuredPoints={measuredPoints}
          possiblePoints={possiblePoints}
          unmeasuredDomains={unmeasuredDomains}
        />
      </div>
      {explanation && (
        <p className="mt-3 max-w-[52ch] text-sm leading-normal text-ink-soft">
          {explanation}
        </p>
      )}
    </section>
  );
}
