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
    <div className="flex min-w-0 flex-col gap-6 py-4 pb-12 @max-[560px]:gap-4">
      <div className="grid min-w-0 grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] items-stretch gap-6 @max-[1180px]:grid-cols-1">
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

      <div className="grid min-w-0 grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] gap-6 @max-[1180px]:grid-cols-1">
        <section className="min-w-0">
          <header className="mb-5 flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="eyebrow">Record states</p>
              <h2 className="mt-1 font-heading text-lg font-semibold tracking-tight text-ink">
                How records are classified
              </h2>
            </div>
            <div className="ml-auto flex flex-wrap gap-2 print:hidden">
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
          </header>
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

        <section className="min-w-0">
          <header className="mb-5">
            <p className="eyebrow">Quality dimensions</p>
            <h2 className="mt-1 font-heading text-lg font-semibold tracking-tight text-ink">
              Scores by area
            </h2>
          </header>
          <DomainScoreBars
            domainScores={domainScores}
            unmeasuredDomains={unmeasuredDomains}
          />
        </section>
      </div>

      <div className="grid min-w-0 grid-cols-3 items-stretch gap-6 @max-[1180px]:grid-cols-1">
        <OverviewCreatedPeriod
          series={createdInPeriod ?? []}
          periodFrom={periodFrom}
          periodTo={periodTo}
          clockLabel={clockLabel}
          depthLabel={depthLabel}
        />

        <section className="flex h-[380px] min-w-0 flex-col overflow-hidden">
          <header className="mb-3 shrink-0">
            <p className="eyebrow">Biggest movers</p>
            <h2 className="mt-1 font-heading text-lg font-semibold tracking-tight text-ink">
              Since the last check
            </h2>
          </header>
          <div className="min-h-0 flex-1 overflow-auto">
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
