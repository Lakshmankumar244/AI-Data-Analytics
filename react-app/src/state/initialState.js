// Default scan configuration - values match the confirmed defaults documented
// in the decisions log (§A2 / D8), sourced from the original widget's config object.
export const defaultRuleConfig = {
  staleDays: 365,
  minRecordsPerUser: 25,
  burstSize: 15,
  burstWindowMinutes: 5,
  repeatedValueThreshold: 5,
  duplicateSuspectedFloor: 0.7,
  duplicateConfirmedFloor: 0.9,
  excludeBulkUsers: true,
  stageAware: true,
  matrixMinObservations: 20, // D10 - now disclosed + configurable, not hidden
};

export const defaultScanConfig = {
  modules: [], // populated from the connection's accessible module list
  depth: "presales", // quick | presales | deep | full
  clock: "created", // created | modified
  range: { id: "90d", from: null, to: null },
  rules: defaultRuleConfig,
};

const STORAGE_KEY = "scan-config-v2";

export function loadPersistedScanConfig() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function persistScanConfig(scanConfig) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(scanConfig));
  } catch {
    // storage unavailable - not fatal, just skip persistence
  }
}

export function buildInitialState() {
  return {
    phase: "boot", // boot | home | setup | running | report | error
    connection: "loading",
    scanHistory: [],
    historyNeedsRefresh: false,
    connectionNotice: null, // soft, non-fatal message shown on the connect panel (e.g. consent declined)
    scanConfig: loadPersistedScanConfig() ?? defaultScanConfig,
    progress: {}, // module api_name -> { scanned, estimatedTotal, phase }
    completedModules: [],
    apiStats: { dispatched: 0, retried: 0, failed: 0 },
    scanId: null,
    scanContext: null,
    scan: null, // populated once the scan lands in "report" phase
    tab: "overview",
    filterModules: [],
    focusState: null,
    errorMessage: null,
  };
}
