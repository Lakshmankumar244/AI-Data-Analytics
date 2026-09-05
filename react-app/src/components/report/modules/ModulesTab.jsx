import { useAppState } from "../../../state/AppContext";
import { DOMAIN_LABELS } from "../../../utils/bands";
import LoadingState from "../../shared/LoadingState";
import FieldQualityTable from "./FieldQualityTable";
import ModuleMatrix from "./ModuleMatrix";

const DOMAIN_ORDER = [
  "completeness",
  "duplication",
  "validity",
  "plausibility",
  "freshness",
  "integrity",
  "config",
  "pii",
  "automation",
];

export default function ModulesTab() {
  const { scan, filterModules, scanConfig } = useAppState();
  if (!scan?.moduleFindings) {
    return <LoadingState label="Loading module analytics" />;
  }

  const minObservations = scanConfig.rules.matrixMinObservations;
  const visibleModules = scan.moduleFindings.filter(
    (module) =>
      filterModules.length === 0 || filterModules.includes(module.apiName)
  );
  const measuredDomainOrder = DOMAIN_ORDER.filter((domain) =>
    visibleModules.some((module) => typeof module.domains[domain] === "number")
  );

  return (
    <div className="flex min-w-0 flex-col gap-10 py-6 pb-12 @max-[720px]:py-4 @max-[720px]:pb-8">
      <section className="min-w-0">
        <header className="mb-2.5">
          <p className="eyebrow">Modules</p>
        </header>
        <ModuleMatrix
          modules={visibleModules}
          domainOrder={measuredDomainOrder}
          domainLabels={DOMAIN_LABELS}
          minObservations={minObservations}
        />
      </section>

      {visibleModules.map((module) => (
        <section className="min-w-0 border-t border-line pt-8" key={module.apiName}>
          <header className="mb-2.5 flex flex-wrap items-start justify-between gap-2.5">
            <div>
              <p className="eyebrow">{module.label}</p>
              <h2 className="mt-0.5 font-heading text-base font-semibold tracking-tight text-ink">
                Field quality
              </h2>
              <p className="mt-0.5 text-xs text-ink-muted">
                {module.recordCount.toLocaleString("en-IN")} records analyzed
              </p>
            </div>
            <div
              className="flex flex-wrap gap-x-4 gap-y-1"
              aria-label="Measured scores"
            >
              {DOMAIN_ORDER.filter(
                (domain) => typeof module.domains[domain] === "number"
              ).map((domain) => (
                <span key={domain} className="text-[11px] text-ink-soft">
                  {DOMAIN_LABELS[domain]}{" "}
                  <strong className="mono ml-1 font-semibold text-ink">
                    {module.domains[domain]}
                  </strong>
                </span>
              ))}
            </div>
          </header>

          <FieldQualityTable fields={module.fields} />

          <div className="mt-4">
            <p className="eyebrow text-attention">Recommended attention</p>
            <ul className="mt-2 mb-0 list-disc space-y-1.5 pl-[18px] text-xs text-ink-soft">
              {module.recommendations.map((recommendation) => (
                <li key={recommendation}>{recommendation}</li>
              ))}
            </ul>
          </div>
        </section>
      ))}
    </div>
  );
}
