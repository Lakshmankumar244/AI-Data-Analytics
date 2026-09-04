const DOMAIN_WEIGHTS = {
  completeness: 20,
  duplication: 20,
  validity: 15,
  plausibility: 10,
  freshness: 10,
  integrity: 10,
  config: 8,
  pii: 4,
  automation: 3,
};

const UNSUPPORTED_REASON =
  "The current aggregate pipeline does not calculate this domain yet.";

function percent(rate) {
  return typeof rate === "number" ? Math.round(rate * 100) : null;
}

function fieldLabel(apiName) {
  return String(apiName || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function domainScore(domain) {
  return domain?.applicable && Number.isFinite(Number(domain.score))
    ? Math.max(0, Math.min(100, Math.round(Number(domain.score))))
    : null;
}

function measuredScore(scores) {
  const domains = Object.entries(scores)
    .map(([domain, score]) => ({ domain, score }))
    .filter((item) => item.score !== null && DOMAIN_WEIGHTS[item.domain]);
  const points = domains.reduce(
    (sum, domain) => sum + DOMAIN_WEIGHTS[domain.domain],
    0
  );
  return points
    ? Math.round(
        domains.reduce(
          (sum, domain) =>
            sum + domain.score * DOMAIN_WEIGHTS[domain.domain],
          0
        ) / points
      )
    : null;
}

export function buildModuleFindings(module) {
  const summary = module.metrics?.summary?.data ?? {};
  const completenessFields = module.metrics?.completeness?.data?.fields ?? {};
  const validityFields = module.metrics?.validity?.data?.fields ?? {};
  const completeness = percent(summary.completenessRate);
  const validity = percent(summary.validityRate);
  const storedDomains = module.metrics?.domains?.data?.domains ?? {};
  const duplication = domainScore(storedDomains.duplication);
  const plausibility = domainScore(storedDomains.plausibility);
  const freshness = domainScore(storedDomains.freshness);
  const integrity = domainScore(storedDomains.integrity);
  const config = domainScore(storedDomains.config);
  const pii = domainScore(storedDomains.pii);
  const automation = domainScore(storedDomains.automation);

  const fields = Object.keys(completenessFields)
    .map((apiName) => {
      const completenessData = completenessFields[apiName] ?? {};
      const validityData = validityFields[apiName] ?? null;
      const completenessScore = percent(completenessData.rate);
      const validityScore = percent(validityData?.rate);
      return {
        apiName,
        label: fieldLabel(apiName),
        populated: Number(completenessData.populated) || 0,
        empty: Number(completenessData.empty) || 0,
        completeness: completenessScore,
        checked: validityData ? Number(validityData.checked) || 0 : null,
        invalid: validityData ? Number(validityData.invalid) || 0 : null,
        validity: validityScore,
        issueSeverity: Math.max(
          completenessScore === null ? 0 : 100 - completenessScore,
          validityScore === null ? 0 : 100 - validityScore
        ),
      };
    })
    .sort(
      (left, right) =>
        right.issueSeverity - left.issueSeverity ||
        left.label.localeCompare(right.label)
    );

  const recommendations = [
    ...fields
      .filter((field) => field.empty > 0)
      .sort((left, right) => right.empty - left.empty)
      .slice(0, 3)
      .map(
        (field) =>
          `${field.label}: ${field.empty.toLocaleString("en-IN")} records are missing a value.`
      ),
    ...fields
      .filter((field) => field.invalid > 0)
      .sort((left, right) => right.invalid - left.invalid)
      .slice(0, 3)
      .map(
        (field) =>
          `${field.label}: review ${field.invalid.toLocaleString("en-IN")} invalid values.`
      ),
  ].slice(0, 5);

  return {
    apiName: module.moduleApiName,
    label: fieldLabel(module.moduleApiName),
    recordCount: Number(module.sourceRecordCount) || 0,
    overall: measuredScore({
      completeness,
      duplication,
      validity,
      plausibility,
      freshness,
      integrity,
      config,
      pii,
      automation,
    }),
    domains: {
      completeness,
      duplication,
      validity,
      plausibility,
      freshness,
      integrity,
      config,
      pii,
      automation,
    },
    fields,
    recommendations:
      recommendations.length > 0
        ? recommendations
        : ["No completeness or validity issues were detected in this module."],
  };
}

function aggregateAnalytics(modules = []) {
  const totals = {
    records: 0,
    cells: 0,
    populated: 0,
    checked: 0,
    invalid: 0,
    duplicateObservations: 0,
    duplicateOccurrences: 0,
    plausibilityChecks: 0,
    plausibilityFailures: 0,
    freshnessRecords: 0,
    freshnessPoints: 0,
    integrityChecks: 0,
    integrityFailures: 0,
  };
  const reasons = {};

  for (const module of modules) {
    const summary = module.metrics?.summary?.data;
    if (summary) {
      totals.records += Number(summary.recordCount) || 0;
      totals.cells += Number(summary.totalCells) || 0;
      totals.populated += Number(summary.populatedCells) || 0;
      totals.checked += Number(summary.checkedValues) || 0;
      totals.invalid += Number(summary.invalidValues) || 0;
    }
    const domains = module.metrics?.domains?.data?.domains ?? {};
    const duplication = domains.duplication;
    if (duplication?.applicable) {
      totals.duplicateObservations += Number(duplication.observations) || 0;
      totals.duplicateOccurrences += Number(duplication.duplicateOccurrences) || 0;
    } else if (duplication?.reason) {
      reasons.duplication = duplication.reason;
    }
    const plausibility = domains.plausibility;
    if (plausibility?.applicable) {
      totals.plausibilityChecks += Number(plausibility.checksPerformed) || 0;
      totals.plausibilityFailures += Number(plausibility.checksFailed) || 0;
    } else if (plausibility?.reason) {
      reasons.plausibility = plausibility.reason;
    }
    const freshness = domains.freshness;
    if (freshness?.applicable) {
      totals.freshnessRecords += Number(freshness.recordsEvaluated) || 0;
      totals.freshnessPoints += Number(freshness.scorePoints) || 0;
    } else if (freshness?.reason) {
      reasons.freshness = freshness.reason;
    }
    const integrity = domains.integrity;
    if (integrity?.applicable) {
      totals.integrityChecks += Number(integrity.checksPerformed) || 0;
      totals.integrityFailures += Number(integrity.checksFailed) || 0;
    } else if (integrity?.reason) {
      reasons.integrity = integrity.reason;
    }
    for (const domain of ["config", "pii", "automation"]) {
      if (domains[domain]?.reason) reasons[domain] = domains[domain].reason;
    }
  }

  const scores = {
    completeness: totals.cells ? percent(totals.populated / totals.cells) : null,
    duplication: totals.duplicateObservations
      ? percent(
          (totals.duplicateObservations - totals.duplicateOccurrences) /
            totals.duplicateObservations
        )
      : null,
    validity: totals.checked
      ? percent((totals.checked - totals.invalid) / totals.checked)
      : null,
    plausibility: totals.plausibilityChecks
      ? percent(
          (totals.plausibilityChecks - totals.plausibilityFailures) /
            totals.plausibilityChecks
        )
      : null,
    freshness: totals.freshnessRecords
      ? Math.round(totals.freshnessPoints / totals.freshnessRecords)
      : null,
    integrity: totals.integrityChecks
      ? percent(
          (totals.integrityChecks - totals.integrityFailures) /
            totals.integrityChecks
        )
      : null,
    config: null,
    pii: null,
    automation: null,
  };
  const domainScores = Object.entries(DOMAIN_WEIGHTS).map(([domain, weight]) => ({
    domain,
    weight,
    score: scores[domain],
    applicable: scores[domain] !== null,
  }));
  const unmeasuredDomains = domainScores
    .filter((domain) => !domain.applicable)
    .map((domain) => ({
      domain: domain.domain,
      reason: reasons[domain.domain] || UNSUPPORTED_REASON,
    }));
  const measuredPoints = domainScores
    .filter((domain) => domain.applicable)
    .reduce((sum, domain) => sum + domain.weight, 0);
  return {
    overallScore: measuredScore(scores) ?? 0,
    measuredPoints,
    possiblePoints: 100,
    unmeasuredDomains,
    recordsInScope: totals.records,
    domainScores,
  };
}

const EMPTY_STATE_COUNTS = {
  proper: 0,
  incomplete: 0,
  inaccurate: 0,
  suspicious: 0,
  suspected_duplicate: 0,
  confirmed_duplicate: 0,
};

function moduleRecordCount(module) {
  return (
    Number(module.metrics?.summary?.data?.recordCount) ||
    Number(module.sourceRecordCount) ||
    0
  );
}

function moduleStateCounts(module) {
  const findings = module.metrics?.record_findings?.data;
  if (!findings?.measured) return null;
  const stored = findings.stateCounts;
  if (stored && Number.isFinite(Number(stored.proper))) {
    return {
      proper: Number(stored.proper) || 0,
      incomplete: Number(stored.incomplete) || 0,
      inaccurate: Number(stored.inaccurate) || 0,
      suspicious: Number(stored.suspicious) || 0,
      suspected_duplicate: Number(stored.suspected_duplicate) || 0,
      confirmed_duplicate: Number(stored.confirmed_duplicate) || 0,
    };
  }
  const records = moduleRecordCount(module);
  const affected = Number(findings.affectedRecordCount) || 0;
  const missing = Number(findings.missingIssueCount) || 0;
  const invalid = Number(findings.invalidIssueCount) || 0;
  const counts = { ...EMPTY_STATE_COUNTS, proper: Math.max(0, records - affected) };
  if (affected <= 0) return counts;
  if (invalid === 0) return { ...counts, incomplete: affected };
  if (missing === 0) return { ...counts, inaccurate: affected };
  // Older scans store issue totals, not exclusive record states. All
  // affected records have quality issues; keep the buckets additive.
  return { ...counts, incomplete: affected };
}

export function aggregateStateBreakdown(modules = []) {
  const totals = { ...EMPTY_STATE_COUNTS };
  let measured = false;
  for (const module of modules) {
    const counts = moduleStateCounts(module);
    if (!counts) continue;
    measured = true;
    for (const state of Object.keys(EMPTY_STATE_COUNTS)) {
      totals[state] += counts[state];
    }
  }
  return measured ? totals : null;
}

export function createdInPeriodFromModules(modules = [], findings = []) {
  const scores = new Map(
    findings.map((module) => [module.apiName, module.overall])
  );
  return modules
    .filter((module) => module.moduleApiName)
    .map((module) => ({
      moduleApiName: module.moduleApiName,
      label: fieldLabel(module.moduleApiName),
      recordCount: moduleRecordCount(module),
      score: scores.get(module.moduleApiName) ?? null,
    }));
}

export function summarizeModuleAnalytics(modules = []) {
  const moduleFindings = modules.map(buildModuleFindings);
  return {
    ...aggregateAnalytics(modules),
    stateBreakdown: aggregateStateBreakdown(modules),
    createdInPeriod: createdInPeriodFromModules(modules, moduleFindings),
    moduleFindings,
  };
}

export function adaptAnalyticsResults(results) {
  const modules = results.modules ?? [];
  const moduleFindings = modules.map(buildModuleFindings);
  const prior = Number(results.priorScore);

  return {
    scanId: results.scanId,
    scope: "personal",
    ...aggregateAnalytics(modules),
    priorScore: Number.isFinite(prior) ? Math.round(prior) : null,
    stateBreakdown:
      aggregateStateBreakdown(modules) ?? results.stateBreakdown ?? null,
    createdInPeriod: createdInPeriodFromModules(modules, moduleFindings),
    movers: Array.isArray(results.movers) ? results.movers : [],
    moduleAnalytics: modules,
    moduleFindings,
  };
}
