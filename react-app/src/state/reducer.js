import { defaultScanConfig, persistScanConfig } from "./initialState";

function scanConfigForConnection(scanConfig, connection) {
  if (!Array.isArray(connection?.accessibleModules)) return scanConfig;
  const allowed = new Set(
    connection.accessibleModules
      .filter((module) => Number(module.recordCount) > 0)
      .map((module) => module.apiName)
  );
  const retained = scanConfig.modules.filter((module) => allowed.has(module));
  const modules = retained.length ? retained : Array.from(allowed);
  if (modules.length === scanConfig.modules.length && modules.every((module, index) => module === scanConfig.modules[index])) {
    return scanConfig;
  }
  const next = { ...scanConfig, modules };
  persistScanConfig(next);
  return next;
}

// Phase machine reused from the reverse-engineered widget:
//   boot -> setup -> running -> report (tab/filter changes within report)
//              |________ error
//   reset returns to setup without losing scanConfig

export function reducer(state, action) {
  switch (action.type) {
    case "sessionLoaded": {
      const scanHistory = action.scanHistory ?? [];
      return {
        ...state,
        phase: action.connection || scanHistory.length ? "home" : "setup",
        connection: action.connection,
        scanConfig: scanConfigForConnection(state.scanConfig, action.connection),
        scanHistory,
        historyNeedsRefresh: false,
        connectionNotice: action.notice ?? null,
        errorMessage: null,
      };
    }

    case "connectionLoaded":
      return {
        ...state,
        connection: action.connection,
        scanConfig: scanConfigForConnection(state.scanConfig, action.connection),
        connectionNotice: null,
      };

    case "historyLoaded":
      return {
        ...state,
        scanHistory: action.scanHistory ?? [],
        historyNeedsRefresh: false,
      };

    // Soft outcome: the user backed out of Zoho's consent screen, or the
    // backend otherwise didn't complete the connection. Not a hard error -
    // stay on the connect panel with a quiet explanation instead of
    // dropping into ErrorState.
    case "connectionDeclined":
      return { ...state, connection: null, connectionNotice: action.message };

    case "setScanConfig": {
      const scanConfig = { ...state.scanConfig, ...action.patch };
      persistScanConfig(scanConfig);
      return { ...state, scanConfig };
    }

    case "setRules": {
      const scanConfig = {
        ...state.scanConfig,
        rules: { ...state.scanConfig.rules, ...action.patch },
      };
      persistScanConfig(scanConfig);
      return { ...state, scanConfig };
    }

    case "scanStarted":
      return {
        ...state,
        phase: "running",
        scanId: action.scanId,
        scanContext: action.scanContext ?? null,
        scanConfig: action.scanConfigPatch
          ? { ...state.scanConfig, ...action.scanConfigPatch }
          : state.scanConfig,
        progress: {},
        completedModules: [],
        apiStats: { dispatched: 0, retried: 0, failed: 0 },
      };

    case "progressUpdate":
      return {
        ...state,
        progress: { ...state.progress, [action.module]: action.progress },
        apiStats: action.apiStats ?? state.apiStats,
      };

    case "moduleComplete":
      return {
        ...state,
        completedModules: [...state.completedModules, action.module],
      };

    case "scanComplete":
      return {
        ...state,
        phase: "report",
        scanId: action.scanId ?? action.scan?.scanId ?? state.scanId,
        scan: action.scan,
        scanContext: null,
        tab: "overview",
        filterModules: [],
        historyNeedsRefresh: action.refreshHistory ?? true,
      };

    case "showHome":
      return {
        ...state,
        phase: "home",
        scanId: null,
        scanContext: null,
        scan: null,
        filterModules: [],
      };

    case "showSetup":
      return { ...state, phase: "setup", scanId: null, scanContext: null, scan: null };

    case "setTab":
      return { ...state, tab: action.tab };

    case "setFilter":
      return { ...state, ...action.patch };

    case "error":
      return { ...state, phase: "error", errorMessage: action.message };

    case "reset":
      return {
        ...state,
        phase: "setup",
        scanId: null,
        scanContext: null,
        scan: null,
        progress: {},
        completedModules: [],
        errorMessage: null,
        connectionNotice: null,
        scanConfig: state.scanConfig ?? defaultScanConfig,
      };

    default:
      return state;
  }
}
