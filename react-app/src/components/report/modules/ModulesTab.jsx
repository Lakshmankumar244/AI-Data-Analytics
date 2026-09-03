import { useAppState } from "../../../state/AppContext";
import { DOMAIN_LABELS } from "../../../utils/bands";
import LoadingState from "../../shared/LoadingState";
import FieldQualityTable from "./FieldQualityTable";
import ModuleMatrix from "./ModuleMatrix";
import "./ModulesTab.css";

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
    <div className="modules-tab">
      <section className="panel modules-panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Modules</p>
            <h1>Measured quality by module</h1>
          </div>
          <p className="modules-floor-note">
            {measuredDomainOrder.length} of {DOMAIN_ORDER.length} domains measured. Scores based on fewer than{" "}
            <span className="mono">{minObservations}</span> records display as
            N/A. Unsupported or non-applicable domains remain unmeasured.
          </p>
        </div>
        <ModuleMatrix
          modules={visibleModules}
          domainOrder={measuredDomainOrder}
          domainLabels={DOMAIN_LABELS}
          minObservations={minObservations}
        />
      </section>

      {visibleModules.map((module) => (
        <section className="panel module-detail" key={module.apiName}>
          <div className="panel-header module-detail-header">
            <div>
              <p className="eyebrow">{module.label}</p>
              <h2>Field quality</h2>
              <p className="module-detail-count">
                {module.recordCount.toLocaleString("en-IN")} records analyzed
              </p>
            </div>
            <div className="module-domain-summary" aria-label="Measured scores">
              {DOMAIN_ORDER.filter(
                (domain) => typeof module.domains[domain] === "number"
              ).map((domain) => (
                <span key={domain}>
                  {DOMAIN_LABELS[domain]} <strong>{module.domains[domain]}</strong>
                </span>
              ))}
            </div>
          </div>

          <FieldQualityTable fields={module.fields} />

          <div className="module-recommendations">
            <p className="eyebrow">Recommended attention</p>
            <ul>
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
