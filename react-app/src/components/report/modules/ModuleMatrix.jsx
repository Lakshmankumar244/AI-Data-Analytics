import { useRef } from "react";
import { matrixBand, MATRIX_BANDS } from "../../../utils/bands";
import { formatNumber } from "../../../utils/format";
import { exportVisibleTables } from "../../../utils/exportTable";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

function scoreTone(score) {
  const band = matrixBand(score);
  const unmeasured = score === null || score === undefined;
  const weak = !unmeasured && (band.id === "warn" || band.id === "bad");
  const watch = !unmeasured && band.id === "fair";
  return { band, unmeasured, weak, watch };
}

function scoredValue(module, domain, minObservations) {
  const belowFloor = (module.recordCount ?? 0) < minObservations;
  if (belowFloor) return null;
  return domain ? module.domains[domain] : module.overall;
}

function ScoreCell({ score, title, emphasize = false }) {
  const { band, unmeasured, weak, watch } = scoreTone(score);

  return (
    <td
      className="border-b border-line px-3 py-2.5 text-center whitespace-nowrap"
      style={
        unmeasured
          ? undefined
          : {
              background: band.soft,
              color: weak || watch ? band.color : "var(--ink)",
            }
      }
      title={title}
    >
      <span
        className={cn(
          "mono text-[13px] tracking-tight",
          unmeasured ? "text-ink-muted" : "font-semibold",
          emphasize && "text-[15px]"
        )}
      >
        {unmeasured ? "—" : score}
      </span>
    </td>
  );
}

function matrixHighlights(modules, domainOrder, domainLabels, minObservations) {
  let worst = null;
  let best = null;
  for (const module of modules) {
    const overall = scoredValue(module, null, minObservations);
    if (typeof overall === "number" && (!best || overall > best.score)) {
      best = { label: module.label, score: overall };
    }
    for (const domain of domainOrder) {
      const score = scoredValue(module, domain, minObservations);
      if (typeof score !== "number") continue;
      if (!worst || score < worst.score) {
        worst = {
          label: module.label,
          domain: domainLabels[domain],
          score,
        };
      }
    }
  }
  return { worst, best };
}

/**
 * D10's 20-observation floor is applied per module row here (this fixture
 * doesn't carry per-domain eligible-record counts, only a per-module total,
 * so the floor is applied at the row level as an approximation - a real
 * backend response would carry per-cell eligible counts and could apply
 * this per-cell instead).
 */
export default function ModuleMatrix({
  modules,
  domainOrder,
  domainLabels,
  minObservations,
}) {
  const rootRef = useRef(null);
  const { worst, best } = matrixHighlights(
    modules,
    domainOrder,
    domainLabels,
    minObservations
  );
  const legendBands = [...MATRIX_BANDS].reverse();

  return (
    <section
      ref={rootRef}
      className="flex min-w-0 flex-col rounded-md border border-line bg-surface p-5 @min-[640px]:p-6"
    >
      <header className="mb-4 flex shrink-0 flex-wrap items-end justify-between gap-3 border-b border-line pb-3">
        <h2 className="font-heading text-xl font-semibold tracking-tight text-ink">
          Modules
        </h2>
        <Button
          type="button"
          variant="link"
          size="sm"
          className="h-auto px-0 print:hidden"
          onClick={() => exportVisibleTables(rootRef.current, "module-matrix")}
        >
          Export
        </Button>
      </header>

      <div className="min-w-0 overflow-x-auto overscroll-x-contain">
        <table className="w-full min-w-[56rem] border-separate border-spacing-0 text-[13px]">
          <caption className="sr-only">
            Module quality comparison across completeness, duplication, validity,
            plausibility, freshness, referential integrity, and overall score
          </caption>
          <thead>
            <tr>
              <th className="sticky left-0 z-[1] border-b border-line bg-surface py-2.5 pr-4 text-left align-middle">
                <span className="eyebrow">Module</span>
              </th>
              <th className="border-b border-line px-3 py-2.5 text-right align-middle">
                <span className="eyebrow">Records</span>
              </th>
              {domainOrder.map((domain) => (
                <th
                  key={domain}
                  className="border-b border-line px-3 py-2.5 text-center align-middle"
                >
                  <span className="eyebrow">{domainLabels[domain]}</span>
                </th>
              ))}
              <th className="border-b border-line px-3 py-2.5 text-center align-middle">
                <span className="eyebrow">Overall</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {modules.map((module) => {
              const recordCount = module.recordCount ?? 0;
              const belowFloor = recordCount < minObservations;
              const floorTitle = `Fewer than ${minObservations} records - not enough to score`;

              return (
                <tr key={module.apiName}>
                  <th
                    scope="row"
                    className="sticky left-0 z-[1] border-b border-line bg-surface py-2.5 pr-4 text-left align-middle font-heading text-[13px] font-semibold tracking-tight whitespace-nowrap text-ink"
                  >
                    {module.label}
                  </th>
                  <td className="mono border-b border-line px-3 py-2.5 text-right whitespace-nowrap text-[13px] text-ink">
                    {formatNumber(recordCount)}
                  </td>
                  {domainOrder.map((domain) => {
                    const score = scoredValue(module, domain, minObservations);
                    return (
                      <ScoreCell
                        key={domain}
                        score={score}
                        title={
                          belowFloor
                            ? floorTitle
                            : score === null || score === undefined
                              ? "Not measured for this module"
                              : `${domainLabels[domain]}: ${score}, ${matrixBand(score).label}`
                        }
                      />
                    );
                  })}
                  <ScoreCell
                    score={scoredValue(module, null, minObservations)}
                    emphasize
                    title={
                      belowFloor
                        ? floorTitle
                        : module.overall === null || module.overall === undefined
                          ? "Not measured for this module"
                          : `Overall: ${module.overall}, ${matrixBand(module.overall).label}`
                    }
                  />
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <span className="text-[11px] text-ink-muted">Worse</span>
        <div className="flex overflow-hidden" aria-hidden="true">
          {legendBands.map((band) => (
            <span
              key={band.id}
              className="size-2.5"
              style={{ background: band.soft }}
              title={band.label}
            />
          ))}
        </div>
        <span className="text-[11px] text-ink-muted">Better</span>
      </div>

      {(worst || best) && (
        <aside
          className="mt-4 border-l-[3px] border-brand bg-brand-soft px-4 py-3"
          role="note"
        >
          {worst && (
            <p className="m-0 text-[13px] font-semibold leading-snug text-brand-strong">
              Worst: {worst.label} · {worst.domain} · {worst.score}
            </p>
          )}
          {best && (
            <p className="mt-1 mb-0 text-[12px] leading-snug text-ink-muted">
              Best: {best.label} · {best.score}
            </p>
          )}
        </aside>
      )}
    </section>
  );
}
