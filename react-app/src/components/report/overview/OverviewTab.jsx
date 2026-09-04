import { useMemo } from "react";
import {
  CalendarRange,
  CircleCheck,
  Layers,
  TriangleAlert,
  Users,
} from "lucide-react";
import { useAppState, useActions } from "../../../state/AppContext";
import { summarizeModuleAnalytics } from "../../../data/analyticsAdapter";
import ScoreGauge from "../../shared/ScoreGauge";
import StateBreakdown from "../../shared/StateBreakdown";
import DomainScoreBars from "./DomainScoreBars";
import MoversList from "./MoversList";
import OverviewEmptyNote from "./OverviewEmptyNote";
import OverviewKpiCard from "./OverviewKpiCard";
import { RECORD_STATES } from "../../../utils/bands";
import { formatNumber } from "../../../utils/format";
import { Button } from "@/components/ui/button";
import { ResponsiveGrid } from "../../layout";
import "./OverviewTab.css";

const CLOCK_LABELS = {
  created: "Created date",
  modified: "Modified date",
  Created_Time: "Created date",
  Modified_Time: "Modified date",
};

const GENERIC_FINDING =
  "No completeness or validity issues were detected in this module.";

function formatContextDate(value) {
  if (!value) return null;
  const normalized = String(value).replace(
    /^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})(?::\d{3})?/,
    "$1T$2"
  );
  const date = new Date(normalized);
  return Number.isNaN(date.getTime())
    ? String(value)
    : new Intl.DateTimeFormat("en-IN", {
        dateStyle: "medium",
      }).format(date);
}

function attentionFromBreakdown(breakdown) {
  if (!breakdown) return null;
  return RECORD_STATES.filter((state) => state.id !== "proper").reduce(
    (sum, state) => sum + (breakdown[state.id] ?? 0),
    0
  );
}

function findingsFromModules(moduleFindings = [], filterModules = []) {
  return moduleFindings
    .filter(
      (module) =>
        !filterModules.length || filterModules.includes(module.apiName)
    )
    .flatMap((module) =>
      (module.recommendations ?? [])
        .filter((text) => text && text !== GENERIC_FINDING)
        .map((text) => ({ module: module.label, text }))
    );
}

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

  const moduleCount =
    filterModules.length ||
    scopedScan.moduleAnalytics?.length ||
    scopedScan.moduleFindings?.length ||
    0;
  const cleanRecords = stateBreakdown ? (stateBreakdown.proper ?? 0) : null;
  const attentionRecords = attentionFromBreakdown(stateBreakdown);
  const findings = findingsFromModules(
    scopedScan.moduleFindings,
    filterModules
  );
  const reportContext = scopedScan.reportContext;
  const periodFrom = formatContextDate(reportContext?.fromUtc);
  const periodTo = formatContextDate(reportContext?.toUtc);
  const clockLabel = reportContext?.clock
    ? CLOCK_LABELS[reportContext.clock] || reportContext.clock
    : null;
  const depthLabel = reportContext?.depth
    ? String(reportContext.depth).replace(/^./, (letter) => letter.toUpperCase())
    : null;
  const hasPeriodFacts = Boolean(periodFrom || periodTo || clockLabel || depthLabel);

  return (
    <div className="overview-tab">
      <section className="panel overview-score-panel">
        {scan.reuseNotice && (
          <div className="overview-reuse-notice" role="status">
            {scan.reuseNotice}
          </div>
        )}
        <div className="overview-hero">
          <div className="overview-hero-copy">
            <p className="eyebrow">Measured quality score</p>
            <h1>{formatNumber(recordsInScope)} records checked</h1>
            <p className="overview-hero-lede">
              {moduleCount > 0
                ? `Overall health for the modules in this report across ${formatNumber(moduleCount)} ${moduleCount === 1 ? "module" : "modules"}.`
                : "Overall health for the modules in this report."}
            </p>
            <ul className="overview-hero-facts">
              <li>
                <span>Checked</span>
                <strong className="mono">{formatNumber(recordsInScope)}</strong>
              </li>
              <li>
                <span>Modules</span>
                <strong className="mono">{formatNumber(moduleCount)}</strong>
              </li>
              <li>
                <span>Coverage</span>
                <strong className="mono">
                  {formatNumber(measuredPoints)}/{formatNumber(possiblePoints)}
                </strong>
              </li>
            </ul>
          </div>
          <ScoreGauge
            score={overallScore}
            priorScore={priorScore}
            measuredPoints={measuredPoints}
            possiblePoints={possiblePoints}
            unmeasuredDomains={unmeasuredDomains}
          />
        </div>
      </section>

      <section className="panel overview-snapshot-panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Quality snapshot</p>
            <h2>Where attention is needed</h2>
          </div>
        </div>
        <ResponsiveGrid min="168px" gap="var(--sp-3)" className="overview-kpi-grid">
          <OverviewKpiCard
            label="Clean records"
            value={cleanRecords}
            tone="strong"
            icon={CircleCheck}
            hint={
              cleanRecords === null
                ? "Record-level classification is not included in the current aggregate scan."
                : "Records currently classified as proper."
            }
          />
          <OverviewKpiCard
            label="Need attention"
            value={attentionRecords}
            tone="attention"
            icon={TriangleAlert}
            hint={
              attentionRecords === null
                ? "Record-level classification is not included in the current aggregate scan."
                : "Records in an incomplete, inaccurate, suspicious, or duplicate state."
            }
          />
          <OverviewKpiCard
            label="Users needing help"
            value={null}
            tone="neutral"
            icon={Users}
            hint="User-level help ranking is not available on this scan."
          />
          <OverviewKpiCard
            label="Modules in scope"
            value={moduleCount}
            tone="neutral"
            icon={Layers}
            hint="Modules included in the current report view."
          />
        </ResponsiveGrid>
      </section>

      <div className="overview-primary-grid">
        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Record states</p>
              <h2>How records are classified</h2>
            </div>
            {focusState && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="overview-clear-focus"
                onClick={() => setFilter({ focusState: null })}
              >
                Clear focus
              </Button>
            )}
          </div>
          {stateBreakdown ? (
            <StateBreakdown
              breakdown={stateBreakdown}
              focusState={focusState}
              onFocus={(id) => setFilter({ focusState: id })}
            />
          ) : (
            <OverviewEmptyNote>
              Record-level classification is not included in the current aggregate
              scan.
            </OverviewEmptyNote>
          )}
        </section>

        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Health by area</p>
              <h2>Scores by quality dimension</h2>
            </div>
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
            <div>
              <p className="eyebrow">Created in period</p>
              <h2>Scan window</h2>
            </div>
            <CalendarRange className="overview-panel-icon" aria-hidden="true" />
          </div>
          {hasPeriodFacts ? (
            <dl className="overview-period-facts">
              {(periodFrom || periodTo) && (
                <div>
                  <dt>Period</dt>
                  <dd className="mono">
                    {periodFrom || "—"} – {periodTo || "—"}
                  </dd>
                </div>
              )}
              {clockLabel && (
                <div>
                  <dt>Attribution</dt>
                  <dd>{clockLabel}</dd>
                </div>
              )}
              {depthLabel && (
                <div>
                  <dt>Depth</dt>
                  <dd>{depthLabel}</dd>
                </div>
              )}
            </dl>
          ) : (
            <OverviewEmptyNote>
              Period details are not attached to this report.
            </OverviewEmptyNote>
          )}
        </section>

        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Biggest changes</p>
              <h2>Since the last check</h2>
            </div>
          </div>
          <MoversList movers={movers} />
        </section>

        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Key findings</p>
              <h2>Issues already measured</h2>
            </div>
          </div>
          {findings.length > 0 ? (
            <ul className="overview-findings-list">
              {findings.map((finding) => (
                <li key={`${finding.module}-${finding.text}`}>
                  <span className="overview-finding-module">{finding.module}</span>
                  <span>{finding.text}</span>
                </li>
              ))}
            </ul>
          ) : (
            <OverviewEmptyNote>
              No completeness or validity findings are available for the modules
              in this view.
            </OverviewEmptyNote>
          )}
        </section>
      </div>
    </div>
  );
}
