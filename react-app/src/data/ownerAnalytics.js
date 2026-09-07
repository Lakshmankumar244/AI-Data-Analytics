const DOMAIN_WEIGHTS = { completeness: 20, validity: 15 };

const STATE_KEYS = [
  "proper",
  "incomplete",
  "inaccurate",
  "suspicious",
  "suspected_duplicate",
  "confirmed_duplicate",
];

function ownerStateCounts(data = {}) {
  const stored = data.stateCounts || data.stateBreakdown;
  if (!stored || typeof stored !== "object") return null;
  const counts = {};
  let measured = false;
  for (const key of STATE_KEYS) {
    const value = Number(stored[key]);
    counts[key] = Number.isFinite(value) ? value : 0;
    if (counts[key] > 0) measured = true;
  }
  return measured || STATE_KEYS.some((key) => stored[key] != null) ? counts : null;
}

function percentage(rate) {
  return typeof rate === "number" ? Math.round(rate * 100) : null;
}

function measuredScore(completeness, validity) {
  const measured = [
    [completeness, DOMAIN_WEIGHTS.completeness],
    [validity, DOMAIN_WEIGHTS.validity],
  ].filter(([score]) => score !== null);
  if (!measured.length) return null;
  return Math.round(
    measured.reduce((sum, [score, weight]) => sum + score * weight, 0) /
      measured.reduce((sum, [, weight]) => sum + weight, 0)
  );
}

export function safeOwnerName(value) {
  const name = String(value || "Unassigned").trim();
  return /^\d{10,}$/.test(name) ? "Unknown owner" : name;
}

export function groupOwnerAnalytics(modules = [], filterModules = []) {
  const selected = new Set(filterModules);
  const grouped = new Map();
  for (const module of modules) {
    if (selected.size && !selected.has(module.moduleApiName)) continue;
    for (const result of module.ownerAnalytics ?? []) {
      const data = result.data ?? {};
      if (!data.ownerKey) continue;
      const owner = grouped.get(data.ownerKey) ?? {
        ownerKey: data.ownerKey,
        ownerName: safeOwnerName(data.ownerName),
        team: data.team || data.teamName || "",
        modules: new Set(),
        recordCount: 0,
        totalCells: 0,
        populatedCells: 0,
        checkedValues: 0,
        invalidValues: 0,
        stateBreakdown: null,
      };
      owner.modules.add(module.moduleApiName);
      if (!owner.team && (data.team || data.teamName)) {
        owner.team = data.team || data.teamName;
      }
      for (const key of [
        "recordCount",
        "totalCells",
        "populatedCells",
        "checkedValues",
        "invalidValues",
      ]) {
        owner[key] += Number(data[key]) || 0;
      }
      const counts = ownerStateCounts(data);
      if (counts) {
        owner.stateBreakdown = owner.stateBreakdown ?? {
          proper: 0,
          incomplete: 0,
          inaccurate: 0,
          suspicious: 0,
          suspected_duplicate: 0,
          confirmed_duplicate: 0,
        };
        for (const key of STATE_KEYS) {
          owner.stateBreakdown[key] += counts[key];
        }
      }
      grouped.set(data.ownerKey, owner);
    }
  }
  return Array.from(grouped.values())
    .map((owner) => {
      const completeness = owner.totalCells
        ? percentage(owner.populatedCells / owner.totalCells)
        : null;
      const validity = owner.checkedValues
        ? percentage(
            (owner.checkedValues - owner.invalidValues) / owner.checkedValues
          )
        : null;
      return {
        ...owner,
        team: owner.team || "",
        modules: Array.from(owner.modules).sort(),
        completeness,
        validity,
        overall: measuredScore(completeness, validity),
      };
    })
    .sort(
      (left, right) =>
        right.recordCount - left.recordCount ||
        left.ownerName.localeCompare(right.ownerName)
    );
}

export function countUsersNeedingHelp(owners, minRecordsPerUser = 25) {
  if (!owners.length) return null;
  return owners.filter(
    (owner) =>
      owner.recordCount >= minRecordsPerUser &&
      owner.overall !== null &&
      owner.overall < 70
  ).length;
}

export function recordOwnerQueryKeys(owners, selectedKeys) {
  if (!selectedKeys?.length) return [];
  const byKey = new Map(owners.map((owner) => [owner.ownerKey, owner]));
  return selectedKeys.map((key) => {
    const owner = byKey.get(key);
    return owner?.ownerName === "Unassigned" ? "__unassigned__" : key;
  });
}
