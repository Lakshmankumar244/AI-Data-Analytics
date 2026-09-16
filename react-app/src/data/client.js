import { buildScanEstimate } from "./scanEstimate";
import { adaptAnalyticsResults } from "./analyticsAdapter";
import { buildUserDetail } from "./userDetail";

// Single entry point for backend data access.

// Same-origin Catalyst function path. catalyst serve and hosted Catalyst both
// expose Advanced I/O functions at /server/<function_name>, so this works
// locally and when deployed without baking in a remote development domain.
const FUNCTION_BASE_URL = "/server/ai_data_analytics_function";

export const ZOHO_CONSENT_URL = `${FUNCTION_BASE_URL}/api/zoho/consent`;
export const SALESFORCE_CONSENT_URL = `${FUNCTION_BASE_URL}/api/salesforce/consent`;

export async function getConnection() {
  const res = await fetch(`${FUNCTION_BASE_URL}/api/zoho/connection`, {
    credentials: "same-origin",
  });
  return readJsonResponse(res, "getConnection");
}

export async function getSalesforceConnection() {
  const res = await fetch(`${FUNCTION_BASE_URL}/api/salesforce/connection`, {
    credentials: "same-origin",
  });
  return readJsonResponse(res, "getSalesforceConnection");
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

export async function activateSalesforceConnection(connectionId) {
  const res = await fetch(
    `${FUNCTION_BASE_URL}/api/salesforce/connections/${encodeURIComponent(connectionId)}/activate`,
    {
      method: "POST",
      credentials: "same-origin",
    }
  );
  return readJsonResponse(res, "activateSalesforceConnection");
}

export async function activateCrmConnection(provider, connectionId) {
  if (provider === "salesforce") {
    return activateSalesforceConnection(connectionId);
  }
  return activateConnection(connectionId);
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

export async function deleteScan(scanId) {
  const res = await fetch(
    `${FUNCTION_BASE_URL}/api/scans/${encodeURIComponent(scanId)}`,
    {
      method: "DELETE",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmScanId: scanId }),
    }
  );
  return readJsonResponse(res, "deleteScan");
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

export async function getScorecard(scanId) {
  const results = await getScanResults(scanId);
  return adaptAnalyticsResults(results);
}

export async function getUserDetail(scanId, filterModules = []) {
  const results = await getScanResults(scanId);
  return buildUserDetail(results.modules ?? [], filterModules);
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
  setListQueryParameter(query, "owners", filters.owners);
  if (filters.q) query.set("q", String(filters.q).trim());
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

export function estimateScan(scopeConfig, accessibleModules = []) {
  return buildScanEstimate(scopeConfig, accessibleModules);
}
