import * as api from "./data/client";
import { adaptAnalyticsResults } from "./data/analyticsAdapter";

const BASE = String(import.meta.env.BASE_URL || "/").replace(/\/$/, "");

function withBase(path) {
  const suffix = path === "/" ? "/" : path;
  return `${BASE}${suffix}` || "/";
}

export function parseLocation(pathname = window.location.pathname) {
  let path = pathname || "/";
  if (BASE && (path === BASE || path.startsWith(`${BASE}/`))) {
    path = path.slice(BASE.length) || "/";
  }
  if (!path.startsWith("/")) path = `/${path}`;
  const parts = path.replace(/\/+$/, "").split("/").filter(Boolean);
  if (parts.length === 0) return { name: "setup" };
  if (parts[0] !== "scans") return { name: "setup" };
  if (parts.length === 1) return { name: "home" };
  const scanId = decodeURIComponent(parts[1] || "");
  if (!scanId) return { name: "home" };
  if (parts.length === 2) return { name: "running", scanId };
  if (parts.length === 3 && parts[2] === "report") {
    return { name: "report", scanId };
  }
  return { name: "setup" };
}

export function pathFor(route) {
  if (route?.name === "home") return withBase("/scans");
  if (route?.name === "running" && route.scanId) {
    return withBase(`/scans/${encodeURIComponent(route.scanId)}`);
  }
  if (route?.name === "report" && route.scanId) {
    return withBase(`/scans/${encodeURIComponent(route.scanId)}/report`);
  }
  return withBase("/");
}

export function routeFromState(phase, scanId) {
  if (phase === "home") return { name: "home" };
  if (phase === "running" && scanId) return { name: "running", scanId };
  if (phase === "report" && scanId) return { name: "report", scanId };
  if (phase === "setup") return { name: "setup" };
  return null;
}

function pathsEqual(left, right) {
  const normalize = (path) =>
    path.length > 1 ? path.replace(/\/+$/, "") : path || "/";
  return normalize(left) === normalize(right);
}

export function navigateTo(route, { replace = false } = {}) {
  if (!route) return;
  const nextPath = pathFor(route);
  if (window.location.pathname === nextPath) return;
  const url = `${nextPath}${window.location.search}${window.location.hash}`;
  const method =
    replace || pathsEqual(window.location.pathname, nextPath)
      ? "replaceState"
      : "pushState";
  window.history[method]({ route }, "", url);
}

function contextFromHistory(scans, scanId, status) {
  const found = (scans ?? []).find((scan) => scan.scanId === scanId);
  if (found) return found;
  if (!status) return { scanId };
  return {
    scanId,
    status: status.status,
    modules: (status.modules ?? [])
      .map((module) => module.moduleApiName)
      .filter(Boolean),
  };
}

export async function resolveRoute(route, scans = []) {
  if (!route || route.name === "setup") {
    return { phase: "setup" };
  }
  if (route.name === "home") {
    return { phase: "home" };
  }

  const scanId = route.scanId;
  if (!scanId) return { phase: "home", urlRoute: { name: "home" } };

  if (route.name === "report") {
    const results = await api.getScanResults(scanId);
    const context = contextFromHistory(scans, scanId);
    return {
      phase: "report",
      scanId,
      scan: { ...adaptAnalyticsResults(results), reportContext: context },
    };
  }

  const status = await api.getScanStatus(scanId);
  const context = contextFromHistory(scans, scanId, status);
  return { phase: "running", scanId, scanContext: context };
}

export function dispatchResolved(dispatch, resolved, { session = false, connection, scans, notice } = {}) {
  if (session) {
    dispatch({
      type: "sessionLoaded",
      connection,
      scanHistory: scans ?? [],
      notice,
      phase: resolved.phase,
      scanId: resolved.scanId ?? null,
      scan: resolved.scan ?? null,
      scanContext: resolved.scanContext ?? null,
    });
    return;
  }
  if (resolved.phase === "home") {
    dispatch({ type: "showHome" });
    return;
  }
  if (resolved.phase === "setup") {
    dispatch({ type: "showSetup" });
    return;
  }
  if (resolved.phase === "running") {
    dispatch({
      type: "scanStarted",
      scanId: resolved.scanId,
      scanContext: resolved.scanContext ?? null,
    });
    return;
  }
  if (resolved.phase === "report") {
    dispatch({
      type: "scanComplete",
      scanId: resolved.scanId,
      scan: resolved.scan,
      refreshHistory: false,
    });
  }
}
