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
    <section className="panel overview-hero">
      {reuseNotice && (
        <div className="overview-reuse-notice" role="status">
          {reuseNotice}
        </div>
      )}
      <p className="eyebrow">Overall health</p>
      <h2 className="sr-only">Overall health</h2>
      <div className="overview-hero-score">
        <ScoreGauge
          score={overallScore}
          priorScore={priorScore}
          measuredPoints={measuredPoints}
          possiblePoints={possiblePoints}
          unmeasuredDomains={unmeasuredDomains}
        />
      </div>
      {explanation ? (
        <p className="overview-hero-narrative">{explanation}</p>
      ) : (
        <p className="overview-hero-narrative overview-hero-narrative-quiet">
          A dominant issue cannot be named until record states or measured
          dimensions are available.
        </p>
      )}
      {typeof priorScore !== "number" && (
        <p className="overview-hero-compare-empty">
          Prior-period comparison is not available for this scan.
        </p>
      )}
    </section>
  );
}
