import { DOMAIN_LABELS, RECORD_STATES, orgBand } from "../../../utils/bands";

const GENERIC_FINDING =
  "No completeness or validity issues were detected in this module.";

export function attentionFromBreakdown(breakdown) {
  if (!breakdown) return null;
  return RECORD_STATES.filter((state) => state.id !== "proper").reduce(
    (sum, state) => sum + (breakdown[state.id] ?? 0),
    0
  );
}

export function shareOf(part, whole) {
  if (part === null || part === undefined || !whole) return null;
  return (part / whole) * 100;
}

export function findingsFromModules(moduleFindings = [], filterModules = []) {
  return moduleFindings
    .filter(
      (module) =>
        !filterModules.length || filterModules.includes(module.apiName)
    )
    .flatMap((module) =>
      (module.recommendations ?? [])
        .filter((text) => text && text !== GENERIC_FINDING)
        .map((text) => ({
          module: module.label,
          text,
          kind: text.includes("invalid") ? "Validity" : "Completeness",
        }))
    );
}

export function duplicateCountFromModules(modules = []) {
  let measured = false;
  let total = 0;
  for (const module of modules) {
    const duplication = module.metrics?.domains?.data?.domains?.duplication;
    if (!duplication?.applicable) continue;
    measured = true;
    total += Number(duplication.duplicateOccurrences) || 0;
  }
  return measured ? total : null;
}

export function dominantIssue({
  stateBreakdown,
  domainScores,
  recordsInScope,
}) {
  if (stateBreakdown && recordsInScope) {
    const classified = RECORD_STATES.filter((state) => state.id !== "proper")
      .map((state) => ({
        ...state,
        count: stateBreakdown[state.id] ?? 0,
      }))
      .sort((left, right) => right.count - left.count);
    const top = classified[0];
    if (top?.count > 0) {
      const pct = Math.round((top.count / recordsInScope) * 100);
      return `${pct}% of records checked this period are ${top.label.toLowerCase()} — the largest classified issue.`;
    }
  }

  const measured = (domainScores ?? []).filter(
    (domain) => domain.applicable && Number.isFinite(Number(domain.score))
  );
  if (measured.length) {
    const weakest = measured.reduce((current, next) =>
      next.score < current.score ? next : current
    );
    const label = DOMAIN_LABELS[weakest.domain] ?? weakest.domain;
    return `${label} is the weakest measured area at ${weakest.score}.`;
  }

  return null;
}

export function groupDomainScores(domainScores = [], unmeasuredDomains = []) {
  const groups = {
    attention: [],
    healthy: [],
    unavailable: [],
  };

  for (const domain of domainScores) {
    if (!domain.applicable) {
      groups.unavailable.push({
        ...domain,
        reason: unmeasuredDomains.find((item) => item.domain === domain.domain)?.reason,
      });
      continue;
    }
    const band = orgBand(domain.score);
    if (band.id === "strong" || band.id === "stable") {
      groups.healthy.push(domain);
    } else {
      groups.attention.push(domain);
    }
  }

  groups.attention.sort((left, right) => left.score - right.score);
  groups.healthy.sort((left, right) => left.score - right.score);
  return groups;
}
