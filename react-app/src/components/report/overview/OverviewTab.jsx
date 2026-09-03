import { useMemo } from "react";
import { useAppState, useActions } from "../../../state/AppContext";
import { summarizeModuleAnalytics } from "../../../data/analyticsAdapter";
import ScoreGauge from "../../shared/ScoreGauge";
import StateBreakdown from "../../shared/StateBreakdown";
import Band from "../../shared/Band";
import DomainScoreBars from "./DomainScoreBars";
import MoversList from "./MoversList";
import { orgBand } from "../../../utils/bands";
import { formatNumber } from "../../../utils/format";
import {
  MOCK_CREATED_IN_PERIOD,
  MOCK_GAUGE_META,
  MOCK_KEY_FINDINGS,
  MOCK_MOVERS,
  MOCK_STATE_BREAKDOWN,
  MOCK_STAT_CARDS,
} from "./overviewMockData";
import "./OverviewTab.css";

const FINDING_BANDS = {
  critical: {
    id: "critical",
    label: "Critical",
    color: "var(--risk)",
    soft: "var(--risk-soft)",
  },
  high: {
    id: "high",
    label: "High",
    color: "var(--attention)",
    soft: "var(--attention-soft)",
  },
  medium: {
    id: "medium",
    label: "Medium",
    color: "var(--stable)",
    soft: "var(--stable-soft)",
  },
};

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
  const stateBreakdownIsPreview = !stateBreakdown;
  const displayedStateBreakdown = stateBreakdown ?? MOCK_STATE_BREAKDOWN;
  const moversArePreview = !movers?.length;
  const displayedMovers = moversArePreview ? MOCK_MOVERS : movers;
  const availableModuleCount =
    filterModules.length || scopedScan.moduleAnalytics?.length || 0;
  const moduleCount = availableModuleCount || MOCK_GAUGE_META.modules;

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
        <div className="overview-gauge-stats" aria-label="Scan summary">
          <div>
            <span>Checked</span>
            <strong className="mono">{formatNumber(recordsInScope)}</strong>
          </div>
          <div>
            <span>Duplicates</span>
            <strong className="mono">
              {formatNumber(MOCK_GAUGE_META.duplicates)}
            </strong>
          </div>
          <div>
            <span>Modules</span>
            <strong className="mono">{formatNumber(moduleCount)}</strong>
          </div>
        </div>
      </section>

      <section className="panel overview-stats-panel">
        <div className="panel-header">
          <p className="eyebrow">Quality snapshot</p>
          <p className="eyebrow overview-preview-label">(preview data)</p>
        </div>
        <div className="overview-stat-grid">
          {MOCK_STAT_CARDS.map((stat) => {
            const band = orgBand(stat.score);
            return (
              <article
                key={stat.id}
                className={`overview-stat overview-stat-${stat.id}`}
                style={{
                  "--overview-stat-color": band.color,
                  "--overview-stat-soft": band.soft,
                }}
              >
                <span>{stat.label}</span>
                <strong className="mono">{formatNumber(stat.value)}</strong>
              </article>
            );
          })}
        </div>
      </section>

      <div className="overview-primary-grid">
        <section className="panel">
          <div className="panel-header">
            <p className="eyebrow">Record states</p>
            <div className="overview-panel-actions">
              {stateBreakdownIsPreview && (
                <p className="eyebrow overview-preview-label">(preview data)</p>
              )}
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
          </div>
          <StateBreakdown
            breakdown={displayedStateBreakdown}
            focusState={focusState}
            onFocus={(id) => setFilter({ focusState: id })}
          />
        </section>

        <section className="panel">
          <div className="panel-header">
            <p className="eyebrow">Scores by area</p>
          </div>
          <DomainScoreBars
            domainScores={domainScores}
            unmeasuredDomains={unmeasuredDomains}
          />
        </section>
      </div>

      <div className="overview-insights-grid">
        <section className="panel overview-created-panel">
          <div className="panel-header">
            <p className="eyebrow">Created in period</p>
            <p className="eyebrow overview-preview-label">(preview data)</p>
          </div>
          <div
            className="overview-created-chart"
            aria-label="Created in period score chart"
          >
            {MOCK_CREATED_IN_PERIOD.map((period) => {
              const band = orgBand(period.score);
              return (
                <div className="overview-created-column" key={period.label}>
                  <span className="mono overview-created-value">
                    {period.score}
                  </span>
                  <div className="overview-created-track">
                    <span
                      className="overview-created-bar"
                      style={{
                        height: `${period.score}%`,
                        background: band.color,
                      }}
                    />
                  </div>
                  <span className="mono overview-created-label">
                    {period.label}
                  </span>
                </div>
              );
            })}
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <p className="eyebrow">Biggest changes</p>
            {moversArePreview && (
              <p className="eyebrow overview-preview-label">(preview data)</p>
            )}
          </div>
          <MoversList movers={displayedMovers} />
        </section>

        <section className="panel">
          <div className="panel-header">
            <p className="eyebrow">Key findings</p>
            <p className="eyebrow overview-preview-label">(preview data)</p>
          </div>
          <ul className="overview-findings-list">
            {MOCK_KEY_FINDINGS.map((finding) => (
              <li key={`${finding.severity}-${finding.text}`}>
                <Band band={FINDING_BANDS[finding.severity]} />
                <span>{finding.text}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
