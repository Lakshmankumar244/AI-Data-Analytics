import { DOMAIN_LABELS, RECORD_STATES, userBand } from "../../../utils/bands";

function mixTotal(breakdown) {
  if (!breakdown) return 0;
  return (
    (Number(breakdown.proper) || 0) +
    (Number(breakdown.incomplete) || 0) +
    (Number(breakdown.inaccurate) || 0) +
    (Number(breakdown.suspicious) || 0) +
    (Number(breakdown.suspected_duplicate) || 0) +
    (Number(breakdown.confirmed_duplicate) || 0)
  );
}

export function isInsufficient(owner, minRecords) {
  return (owner.recordCount ?? 0) < minRecords;
}

export function userCleanShare(owner, minRecords) {
  if (isInsufficient(owner, minRecords)) return null;
  const total = mixTotal(owner.stateBreakdown);
  if (total > 0) {
    return Math.round(((Number(owner.stateBreakdown.proper) || 0) / total) * 100);
  }
  return owner.overall;
}

export function userStanding(owner, minRecords) {
  return userBand(userCleanShare(owner, minRecords), isInsufficient(owner, minRecords));
}

function dominantFlaggedState(breakdown) {
  const total = mixTotal(breakdown);
  if (!total) return null;
  const flagged = RECORD_STATES.filter((state) => state.id !== "proper")
    .map((state) => ({
      ...state,
      count: Number(breakdown[state.id]) || 0,
    }))
    .sort((left, right) => right.count - left.count);
  return flagged[0]?.count > 0 ? flagged[0] : null;
}

function weakestMeasuredDomain(owner) {
  const domains = [
    { id: "completeness", score: owner.completeness },
    { id: "validity", score: owner.validity },
  ].filter((domain) => Number.isFinite(Number(domain.score)));
  if (!domains.length) return null;
  return domains.reduce((current, next) =>
    next.score < current.score ? next : current
  );
}

export function suggestedNextStep(owner, minRecords) {
  const standing = userStanding(owner, minRecords);
  if (standing.id === "insufficient" || standing.id === "exemplary" || standing.id === "solid") {
    return standing.action;
  }

  const flagged = dominantFlaggedState(owner.stateBreakdown);
  if (flagged) {
    if (flagged.id === "incomplete") {
      return standing.id === "intervention"
        ? "Review completeness with team lead"
        : "Coach on completeness";
    }
    if (flagged.id === "inaccurate") {
      return standing.id === "intervention"
        ? "Review validity with team lead"
        : "Coach on validity";
    }
    if (flagged.id === "suspicious") {
      return standing.id === "intervention"
        ? "Review suspicious records with team lead"
        : "Review suspicious records";
    }
    if (flagged.id === "suspected_duplicate" || flagged.id === "confirmed_duplicate") {
      return standing.id === "intervention"
        ? "Review duplicates with team lead"
        : "Review duplicate records";
    }
  }

  const weakest = weakestMeasuredDomain(owner);
  if (weakest) {
    const label = (DOMAIN_LABELS[weakest.id] || weakest.id).toLowerCase();
    return standing.id === "intervention"
      ? `Review ${label} with team lead`
      : `Coach on ${label}`;
  }

  return standing.action;
}

export function recordsNeedingActionInsight(owners, minRecords) {
  const needingHelp = (owners ?? []).filter(
    (owner) =>
      !isInsufficient(owner, minRecords) &&
      owner.overall !== null &&
      owner.overall < 70
  );
  if (!needingHelp.length) return null;
  const actionRecords = needingHelp.reduce(
    (sum, owner) => sum + (Number(owner.recordCount) || 0),
    0
  );
  if (!actionRecords) return null;
  const largest = Math.max(...needingHelp.map((owner) => Number(owner.recordCount) || 0));
  const share = Math.round((largest / actionRecords) * 100);
  return `1 user created ${share}% of all records needing action.`;
}
