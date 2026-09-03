// Single entry point for backend data access. Features that have not yet
// received a real backend implementation remain explicitly exported from
// mockClient.js at the bottom of this file.

const FUNCTION_BASE_URL =
  "https://ai-data-analytics-60083091023.development.catalystserverless.in/server/ai_data_analytics_function";
// TODO: replace <name> with your actual project domain. Move to
// process.env.REACT_APP_ZOHO_FUNCTION_URL later - hardcoded for now while
// still actively debugging (same reasoning as the consent redirect earlier).

export async function getConnection() {
  const res = await fetch(`${FUNCTION_BASE_URL}/api/zoho/connection`, {
    credentials: "same-origin",
  });
  return readJsonResponse(res, "getConnection");
}

export async function activateConnection(connectionId) {
  const res = await fetch(
    `${FUNCTION_BASE_URL}/api/zoho/connections/${encodeURIComponent(connectionId)}/activate`,
    {
      method: "POST",
      credentials: "same-origin",
    }
  );
  return readJsonResponse(res, "activateConnection");
}

async function readJsonResponse(res, operation) {
  let body = null;
  try {
    body = await res.json();
  } catch {
    // Preserve the HTTP status when Catalyst returns a non-JSON error page.
  }
  if (!res.ok) {
    const backendMessage = body?.error?.message;
    const error = new Error(
      backendMessage || `${operation} failed: ${res.status}`
    );
    error.code = body?.error?.code || null;
    error.status = res.status;
    error.body = body;
    throw error;
  }
  return body;
}

function setListQueryParameter(query, name, values = []) {
  const normalized = (Array.isArray(values) ? values : [])
    .map((value) => String(value || "").trim())
    .filter(Boolean);
  if (normalized.length) query.set(name, normalized.join(","));
}

export async function startScan(scopeConfig) {
  const res = await fetch(`${FUNCTION_BASE_URL}/api/scans`, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(scopeConfig),
  });
  return readJsonResponse(res, "startScan");
}

export async function getScanHistory() {
  const res = await fetch(`${FUNCTION_BASE_URL}/api/scans`, {
    credentials: "same-origin",
  });
  return readJsonResponse(res, "getScanHistory");
}

export async function getScanStatus(scanId) {
  const res = await fetch(
    `${FUNCTION_BASE_URL}/api/scans/${encodeURIComponent(scanId)}/status`,
    { credentials: "same-origin" }
  );
  return readJsonResponse(res, "getScanStatus");
}

export async function advanceScan(scanId) {
  const res = await fetch(
    `${FUNCTION_BASE_URL}/api/scans/${encodeURIComponent(scanId)}/advance`,
    {
      method: "POST",
      credentials: "same-origin",
    }
  );
  return readJsonResponse(res, "advanceScan");
}

export async function getScanResults(scanId) {
  const res = await fetch(
    `${FUNCTION_BASE_URL}/api/scans/${encodeURIComponent(scanId)}/results`,
    { credentials: "same-origin" }
  );
  return readJsonResponse(res, "getScanResults");
}

export async function getTrend(scanId, modules = []) {
  const query = new URLSearchParams();
  setListQueryParameter(query, "modules", modules);
  const suffix = query.size ? `?${query.toString()}` : "";
  const res = await fetch(
    `${FUNCTION_BASE_URL}/api/scans/${encodeURIComponent(scanId)}/trend${suffix}`,
    { credentials: "same-origin" }
  );
  return readJsonResponse(res, "getTrend");
}

export async function getRecords(scanId, filters = {}, page = 1) {
  const query = new URLSearchParams({ page: String(page) });
  setListQueryParameter(query, "states", filters.states);
  setListQueryParameter(query, "modules", filters.modules);
  const res = await fetch(
    `${FUNCTION_BASE_URL}/api/scans/${encodeURIComponent(scanId)}/records?${query.toString()}`,
    { credentials: "same-origin" }
  );
  return readJsonResponse(res, "getRecords");
}

export async function getFixPlan(scanId, modules = []) {
  const query = new URLSearchParams();
  setListQueryParameter(query, "modules", modules);
  const suffix = query.size ? `?${query.toString()}` : "";
  const res = await fetch(
    `${FUNCTION_BASE_URL}/api/scans/${encodeURIComponent(scanId)}/fix-plan${suffix}`,
    { credentials: "same-origin" }
  );
  return readJsonResponse(res, "getFixPlan");
}

export {
  estimateScan,
  getScorecard,
  getUserDetail,
} from "./mockClient";
