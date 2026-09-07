import { useAppState } from "../../../state/AppContext";
import { DOMAIN_LABELS } from "../../../utils/bands";
import LoadingState from "../../shared/LoadingState";
import FieldQualityTable from "./FieldQualityTable";
import ModuleMatrix from "./ModuleMatrix";
import { formatNumber } from "../../../utils/format";

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

  if (!visibleModules.length) {
    return (
      <div className="flex min-w-0 flex-col py-4 pb-8 @max-[760px]:py-3 @max-[760px]:pb-6">
        <h2 className="font-heading text-xl font-semibold tracking-tight text-ink">
          Modules
        </h2>
        <p className="mt-2 max-w-[46ch] text-sm leading-relaxed text-ink-soft">
          No modules match the current filters.
        </p>
      </div>
    );
  }

  return (
    <div className="flex min-w-0 flex-col gap-5 py-4 pb-8 @max-[760px]:py-3 @max-[760px]:pb-6">
      <ModuleMatrix
        modules={visibleModules}
        domainOrder={measuredDomainOrder}
        domainLabels={DOMAIN_LABELS}
        minObservations={minObservations}
      />

      {visibleModules.map((module) => (
        <section
          className="min-w-0 rounded-md border border-line bg-surface p-5 @min-[640px]:p-6"
          key={module.apiName}
        >
          <header className="mb-4 border-b border-line pb-3">
            <h2 className="font-heading text-xl font-semibold tracking-tight text-ink">
              {module.label}
            </h2>
            <p className="mt-1 text-sm text-ink-muted">
              {formatNumber(module.recordCount)} records
            </p>
          </header>
          <FieldQualityTable fields={module.fields} />
        </section>
      ))}
    </div>
  );
}
