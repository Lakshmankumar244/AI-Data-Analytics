import { useMemo } from "react";
import { useAppState, useActions } from "../../../state/AppContext";
import { summarizeModuleAnalytics } from "../../../data/analyticsAdapter";
import StateBreakdown from "../../shared/StateBreakdown";
import DomainScoreBars from "./DomainScoreBars";
import MoversList from "./MoversList";
import OverviewEmptyNote from "./OverviewEmptyNote";
import OverviewHealthHero from "./OverviewHealthHero";
import OverviewSignals from "./OverviewSignals";
import OverviewEvidenceStrip from "./OverviewEvidenceStrip";
import OverviewCreatedPeriod from "./OverviewCreatedPeriod";
import OverviewFindings from "./OverviewFindings";
import OverviewCoverageNotice from "./OverviewCoverageNotice";
import {
  attentionFromBreakdown,
  dominantIssue,
  duplicateCountFromModules,
  findingsFromModules,
  shareOf,
} from "./overviewModel";
import {
  countUsersNeedingHelp,
  groupOwnerAnalytics,
} from "../../../data/ownerAnalytics";
import { formatReportDate } from "../../../utils/format";
import { Button } from "@/components/ui/button";
import "./OverviewTab.css";

const CLOCK_LABELS = {
  created: "Created date",
  modified: "Modified date",
  Created_Time: "Created date",
  Modified_Time: "Modified date",
};

export default function OverviewTab() {
  const { scan, focusState, filterModules, filterUsers, scanConfig } = useAppState();
  const { setFilter, setTab } = useActions();

  const scopedScan = useMemo(() => {
    if (!scan || !filterModules.length) return scan;
    const selected = (scan?.moduleAnalytics ?? []).filter((module) =>
      filterModules.includes(module.moduleApiName)
    );
    return { ...scan, ...summarizeModuleAnalytics(selected) };
  }, [filterModules, scan]);

  const scopedModules = useMemo(() => {
    if (!scopedScan?.moduleAnalytics) return [];
    if (!filterModules.length) return scopedScan.moduleAnalytics;
    return scopedScan.moduleAnalytics.filter((module) =>
      filterModules.includes(module.moduleApiName)
    );
  }, [filterModules, scopedScan]);

  const owners = useMemo(
    () => groupOwnerAnalytics(scopedModules, []),
    [scopedModules]
  );
  const visibleOwners = useMemo(() => {
    if (!filterUsers.length) return owners;
    const selected = new Set(filterUsers);
    return owners.filter((owner) => selected.has(owner.ownerKey));
  }, [filterUsers, owners]);

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
    createdInPeriod,
  } = scopedScan;

  const moduleCount =
    filterModules.length ||
    scopedScan.moduleAnalytics?.length ||
    scopedScan.moduleFindings?.length ||
    0;
  const cleanRecords = stateBreakdown ? (stateBreakdown.proper ?? 0) : null;
  const attentionRecords = attentionFromBreakdown(stateBreakdown);
  const suspiciousRecords =
    stateBreakdown && (stateBreakdown.suspicious ?? 0) > 0
      ? stateBreakdown.suspicious
      : null;
  const findings = findingsFromModules(scopedScan.moduleFindings, filterModules);
  const duplicateCount = duplicateCountFromModules(scopedModules);
  const explanation = dominantIssue({
    stateBreakdown,
    domainScores,
    recordsInScope,
  });
  const reportContext = scopedScan.reportContext;
  const periodFrom = formatReportDate(reportContext?.fromUtc);
  const periodTo = formatReportDate(reportContext?.toUtc);
  const clockLabel = reportContext?.clock
    ? CLOCK_LABELS[reportContext.clock] || reportContext.clock
    : null;
  const depthLabel = reportContext?.depth
    ? String(reportContext.depth).replace(/^./, (letter) => letter.toUpperCase())
    : null;
  const visibleMovers = (movers ?? []).filter((mover) => {
    if (mover.type === "module" && filterModules.length) {
      return filterModules.includes(mover.key) || filterModules.includes(mover.label);
    }
    if (mover.type === "user" && filterUsers.length) {
      return filterUsers.includes(mover.key);
    }
    return true;
  });
  const usersNeedingHelp = countUsersNeedingHelp(
    visibleOwners,
    scanConfig?.rules?.minRecordsPerUser ?? 25
  );

  return (
    <div className="overview-tab">
      <div className="overview-executive">
        <OverviewHealthHero
          overallScore={overallScore}
          priorScore={priorScore}
          measuredPoints={measuredPoints}
          possiblePoints={possiblePoints}
          unmeasuredDomains={unmeasuredDomains}
          explanation={explanation}
          reuseNotice={scan.reuseNotice}
        />
        <OverviewSignals
          cleanRecords={cleanRecords}
          attentionRecords={attentionRecords}
          suspiciousRecords={suspiciousRecords}
          cleanShare={shareOf(cleanRecords, recordsInScope)}
          attentionShare={shareOf(attentionRecords, recordsInScope)}
          suspiciousShare={shareOf(suspiciousRecords, recordsInScope)}
          usersNeedingHelp={usersNeedingHelp}
          onOpenUsers={() => setTab("users")}
        />
      </div>

      <OverviewEvidenceStrip
        recordsInScope={recordsInScope}
        duplicateCount={duplicateCount}
        moduleCount={moduleCount}
        measuredPoints={measuredPoints}
        possiblePoints={possiblePoints}
      />

      <div className="overview-quality">
        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Record states</p>
              <h2>How records are classified</h2>
            </div>
            <div className="overview-panel-actions">
              {focusState && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setFilter({ focusState: null })}
                >
                  Clear focus
                </Button>
              )}
              {stateBreakdown && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setTab("records")}
                >
                  Investigate records
                </Button>
              )}
            </div>
          </div>
          {stateBreakdown ? (
            <StateBreakdown
              breakdown={stateBreakdown}
              focusState={focusState}
              onFocus={(id) => setFilter({ focusState: id })}
            />
          ) : (
            <OverviewEmptyNote>
              Record-level classification is not included in the current
              aggregate scan.
            </OverviewEmptyNote>
          )}
        </section>

        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Quality dimensions</p>
              <h2>Scores by area</h2>
            </div>
          </div>
          <DomainScoreBars
            domainScores={domainScores}
            unmeasuredDomains={unmeasuredDomains}
          />
        </section>
      </div>

      <div className="overview-context">
        <OverviewCreatedPeriod
          series={createdInPeriod ?? []}
          periodFrom={periodFrom}
          periodTo={periodTo}
          clockLabel={clockLabel}
          depthLabel={depthLabel}
        />

        <section className="panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Biggest movers</p>
              <h2>Since the last check</h2>
            </div>
          </div>
          <div className="overview-context-body overview-movers-scroll">
            <MoversList movers={visibleMovers} />
          </div>
        </section>

        <OverviewFindings findings={findings} />
      </div>

      <OverviewCoverageNotice
        domainScores={domainScores}
        unmeasuredDomains={unmeasuredDomains}
      />
    </div>
  );
}
