import ScoreGauge from "../../shared/ScoreGauge";
import { DOMAIN_LABELS } from "../../../utils/bands";
import { formatNumber } from "../../../utils/format";

function WhyFact({ label, children, swatch }) {
  return (
    <div className="min-w-0">
      <dt className="eyebrow">{label}</dt>
      <dd className="mt-1 flex min-w-0 items-baseline gap-2 text-[13px] font-medium tracking-tight text-ink">
        {swatch && (
          <span
            className="inline-block size-1.5 shrink-0 rounded-full"
            style={{ background: swatch }}
            aria-hidden="true"
          />
        )}
        <span className="min-w-0">{children}</span>
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
  weakestDomain,
  strongestDomain,
  dominantState,
}) {
  const weakestLabel = weakestDomain
    ? DOMAIN_LABELS[weakestDomain.domain] ?? weakestDomain.domain
    : null;
  const strongestLabel = strongestDomain
    ? DOMAIN_LABELS[strongestDomain.domain] ?? strongestDomain.domain
    : null;
  const sameExtreme =
    weakestDomain &&
    strongestDomain &&
    weakestDomain.domain === strongestDomain.domain;

  return (
    <section className="flex min-w-0 flex-col">
      {reuseNotice && (
        <div
          className="mb-5 border-l-2 border-brand py-2 pl-3 text-[13px] leading-snug text-brand-strong"
          role="status"
        >
          {reuseNotice}
        </div>
      )}
      <p className="eyebrow">How healthy is the CRM</p>
      <h2 className="sr-only">Overall health</h2>
      <div className="mt-3">
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
      {(dominantState || weakestLabel || strongestLabel) && (
        <dl className="mt-5 grid max-w-2xl grid-cols-1 gap-x-8 gap-y-3 sm:grid-cols-3">
          {dominantState && (
            <WhyFact label="Dominant issue" swatch={dominantState.color}>
              {dominantState.label}
              <span className="mono ml-1.5 text-ink-muted">
                {formatNumber(dominantState.count)}
                {Number.isFinite(dominantState.pct) ? ` · ${dominantState.pct}%` : ""}
              </span>
            </WhyFact>
          )}
          {weakestLabel && (
            <WhyFact label="Weakest dimension">
              {weakestLabel}
              <span className="mono ml-1.5 text-ink-muted">{weakestDomain.score}</span>
            </WhyFact>
          )}
          {strongestLabel && !sameExtreme && (
            <WhyFact label="Strongest dimension">
              {strongestLabel}
              <span className="mono ml-1.5 text-ink-muted">{strongestDomain.score}</span>
            </WhyFact>
          )}
        </dl>
      )}
    </section>
  );
}
