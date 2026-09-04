const DOMAIN_WEIGHTS = { completeness: 20, validity: 15 };

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
        modules: new Set(),
        recordCount: 0,
        totalCells: 0,
        populatedCells: 0,
        checkedValues: 0,
        invalidValues: 0,
      };
      owner.modules.add(module.moduleApiName);
      for (const key of [
        "recordCount",
        "totalCells",
        "populatedCells",
        "checkedValues",
        "invalidValues",
      ]) {
        owner[key] += Number(data[key]) || 0;
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
