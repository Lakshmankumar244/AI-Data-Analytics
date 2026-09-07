import { userBand } from "../../../utils/bands";

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
