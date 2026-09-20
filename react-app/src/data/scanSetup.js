export function isSalesforceProvider(activeConnection) {
  return activeConnection?.provider === "salesforce";
}

export function isZohoProvider(activeConnection) {
  return activeConnection?.provider === "zoho";
}

export function salesforceAccessibleModules(metadata) {
  return (Array.isArray(metadata?.objects) ? metadata.objects : [])
    .map((item) => {
      const apiName = String(item?.apiName || "").trim();
      if (!apiName) return null;
      return { apiName, label: apiName };
    })
    .filter(Boolean);
}

export function salesforceOrganizationName(metadata, fallback = "") {
  return String(metadata?.organization?.name || "").trim() || fallback;
}

export function retainedAccessibleModules(selected, accessibleModules) {
  const allowed = new Set(
    (Array.isArray(accessibleModules) ? accessibleModules : []).map(
      (module) => module.apiName
    )
  );
  return (Array.isArray(selected) ? selected : []).filter((name) =>
    allowed.has(name)
  );
}

export function defaultAccessibleModuleNames(accessibleModules) {
  return (Array.isArray(accessibleModules) ? accessibleModules : []).map(
    (module) => module.apiName
  );
}
