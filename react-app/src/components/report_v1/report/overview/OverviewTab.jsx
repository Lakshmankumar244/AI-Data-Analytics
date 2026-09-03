import { useMemo } from "react";
import { useAppState, useActions } from "../../../state/AppContext";
import { summarizeModuleAnalytics } from "../../../data/analyticsAdapter";
import ScoreGauge from "../../shared/ScoreGauge";
import StateBreakdown from "../../shared/StateBreakdown";
import DomainScoreBars from "./DomainScoreBars";
import MoversList from "./MoversList";
import { formatNumber } from "../../../utils/format";
import "./OverviewTab.css";

export default function OverviewTab() {
  const { scan, focusState, filterModules } = useAppState();
  const { setFilter } = useActions();

  const scopedScan = useMemo(() => {
    if (!scan || !filterModules.length) return scan;
    const selected = (scan?.moduleAnalytics ?? []).filter((module) =>
      filterModules.includes(module.moduleApiName)
    );
    return { ...scan, ...summarizeModuleAnalytics(selected) };
  }, [filterModules, scan]);

  if (!scopedScan) return null;

  const {
    overallScore,
    priorScore,
    measuredPoints,
    possiblePoints,
    unmeasuredDomains,
    recordsInScope,
    stateBreakdown,
    domainScores,
    movers,
  } = scopedScan;

  return (
    <div className="overview-tab">
      <section className="panel overview-score-panel">
        {scan.reuseNotice && (
          <div className="overview-reuse-notice" role="status">
            {scan.reuseNotice}
          </div>
        )}
        <div className="panel-header">
          <div>
            <p className="eyebrow">Measured quality score</p>
            <h1>{formatNumber(recordsInScope)} records checked</h1>
          </div>
        </div>
        <ScoreGauge
          score={overallScore}
          priorScore={priorScore}
          measuredPoints={measuredPoints}
          possiblePoints={possiblePoints}
          unmeasuredDomains={unmeasuredDomains}
        />
      </section>

      {stateBreakdown ? (
        <section className="panel">
          <div className="panel-header">
            <p className="eyebrow">Record states</p>
            {focusState && (
              <button
                type="button"
                className="overview-clear-focus"
                onClick={() => setFilter({ focusState: null })}
              >
                Clear focus
              </button>
            )}
          </div>
          <StateBreakdown
            breakdown={stateBreakdown}
            focusState={focusState}
            onFocus={(id) => setFilter({ focusState: id })}
          />
        </section>
      ) : (
        <section className="panel">
          <p className="eyebrow">Record states</p>
          <p className="muted">
            Record-level classification is not included in the current aggregate scan.
          </p>
        </section>
      )}

      <div className="overview-grid">
        <section className="panel">
          <div className="panel-header">
            <p className="eyebrow">Domain scores</p>
          </div>
          <DomainScoreBars domainScores={domainScores} unmeasuredDomains={unmeasuredDomains} />
        </section>

        <section className="panel">
          <div className="panel-header">
            <p className="eyebrow">Biggest changes</p>
          </div>
          <MoversList movers={movers} />
        </section>
      </div>
    </div>
  );
}
