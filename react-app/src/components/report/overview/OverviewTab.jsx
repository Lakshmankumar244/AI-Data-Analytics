import { useMemo } from "react";
import { useAppState, useActions } from "../../../state/AppContext";
import { summarizeModuleAnalytics } from "../../../data/analyticsAdapter";
import { ResponsiveGrid } from "../../layout";
import StateBreakdown from "../../shared/StateBreakdown";
import DomainScoreBars from "./DomainScoreBars";
import OverviewEmptyNote from "./OverviewEmptyNote";
import OverviewHealthHero from "./OverviewHealthHero";
import OverviewSignals from "./OverviewSignals";
import OverviewPanel from "./OverviewPanel";
import OverviewCreatedPeriod from "./OverviewCreatedPeriod";
import MoversList from "./MoversList";
import OverviewFindings from "./OverviewFindings";
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
  const duplicateCount = duplicateCountFromModules(scopedModules);
  const explanation = dominantIssue({
    stateBreakdown,
    domainScores,
    recordsInScope,
  });
  const usersNeedingHelp = countUsersNeedingHelp(
    visibleOwners,
    scanConfig?.rules?.minRecordsPerUser ?? 25
  );
  const findings = findingsFromModules(scopedScan.moduleFindings, filterModules);
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

  function openModule(apiName) {
    setFilter({ filterModules: [apiName] });
    setTab("modules");
  }

  return (
    <div className="flex min-w-0 flex-col gap-5 py-6 pb-10 @max-[760px]:py-4 @max-[760px]:pb-8">
      <div className="grid min-w-0 grid-cols-1 items-stretch gap-5 @min-[900px]:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <OverviewHealthHero
          overallScore={overallScore}
          priorScore={priorScore}
          measuredPoints={measuredPoints}
          possiblePoints={possiblePoints}
          unmeasuredDomains={unmeasuredDomains}
          explanation={explanation}
          reuseNotice={scan.reuseNotice}
          recordsInScope={recordsInScope}
          moduleCount={moduleCount}
          duplicateCount={duplicateCount}
        />
        <div className="h-full min-w-0 @container">
          <OverviewSignals
            cleanRecords={cleanRecords}
            attentionRecords={attentionRecords}
            suspiciousRecords={suspiciousRecords}
            cleanShare={shareOf(cleanRecords, recordsInScope)}
            attentionShare={shareOf(attentionRecords, recordsInScope)}
            usersNeedingHelp={usersNeedingHelp}
            onOpenUsers={() => setTab("users")}
          />
        </div>
      </div>

      <div className="grid min-w-0 grid-cols-1 items-stretch gap-5 @min-[900px]:grid-cols-2">
        <OverviewPanel
          title="Record states"
          actions={
            <>
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
                  size="sm"
                  onClick={() => setTab("records")}
                >
                  Investigate records
                </Button>
              )}
            </>
          }
        >
          {stateBreakdown ? (
            <StateBreakdown
              breakdown={stateBreakdown}
              focusState={focusState}
              onFocus={(id) => {
                if (id) setFilter({ focusState: id });
                setTab("records");
              }}
            />
          ) : (
            <OverviewEmptyNote>
              Record-level classification is not included in this scan.
            </OverviewEmptyNote>
          )}
        </OverviewPanel>

        <OverviewPanel title="Scores by area">
          <DomainScoreBars
            domainScores={domainScores}
            unmeasuredDomains={unmeasuredDomains}
          />
        </OverviewPanel>
      </div>

      <ResponsiveGrid min="16rem" gap="1.25rem">
        <OverviewPanel variant="chart" className="@min-[1100px]:max-h-[380px]">
          <OverviewCreatedPeriod
            series={createdInPeriod ?? []}
            periodFrom={periodFrom}
            periodTo={periodTo}
            clockLabel={clockLabel}
            depthLabel={depthLabel}
          />
        </OverviewPanel>
        <OverviewPanel
          variant="rank"
          title="Biggest movers"
          className="@min-[1100px]:max-h-[380px]"
        >
          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1">
            <MoversList movers={visibleMovers} />
          </div>
        </OverviewPanel>
        <OverviewPanel variant="findings" className="@min-[1100px]:max-h-[380px]">
          <OverviewFindings
            findings={findings}
            onOpenModule={openModule}
            onOpenRecords={stateBreakdown ? () => setTab("records") : undefined}
            onOpenUsers={() => setTab("users")}
          />
        </OverviewPanel>
      </ResponsiveGrid>
    </div>
  );
}
