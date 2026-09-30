import { buildScanEstimate } from "./scanEstimate";
import { adaptAnalyticsResults } from "./analyticsAdapter";
import { buildUserDetail } from "./userDetail";
import { FIX_PAGE_SIZE, normalizeFixRecords } from "./fixRecords";
// Single entry point for backend data access.

// Same-origin Catalyst function path. catalyst serve and hosted Catalyst both
// expose Advanced I/O functions at /server/<function_name>, so this works
// locally and when deployed without baking in a remote development domain.
const FUNCTION_BASE_URL = "/server/ai_data_analytics_function";

export const ZOHO_CONSENT_URL = `${FUNCTION_BASE_URL}/api/zoho/consent`;
export const ZOHO_MARKETPLACE_CONSENT_URL = `${FUNCTION_BASE_URL}/api/zoho/marketplace/consent`;
export const SALESFORCE_CONSENT_URL = `${FUNCTION_BASE_URL}/api/salesforce/consent`;

export function zohoConsentUrl() {
  // Marketplace persist (installations + installation_id) runs only on this
  // grant. Catalyst login_redirect drops ?source=marketplace, so Connect must
  // not depend on that query flag.
  return ZOHO_MARKETPLACE_CONSENT_URL;
}

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

export async function getSalesforceMetadata() {
  const res = await fetch(`${FUNCTION_BASE_URL}/api/salesforce/metadata`, {
    credentials: "same-origin",
  });
  return readJsonResponse(res, "getSalesforceMetadata");
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

export async function getFixRecords(scanId, filters = {}) {
  const query = new URLSearchParams();
  const moduleName = String(filters.module || "").trim();
  if (moduleName) query.set("module", moduleName);
  if (filters.cursor) query.set("cursor", String(filters.cursor));
  query.set("pageSize", String(filters.pageSize || FIX_PAGE_SIZE));
  if (filters.q) query.set("q", String(filters.q).trim());
  setListQueryParameter(query, "owners", filters.owners);
  if (filters.severity) query.set("severity", String(filters.severity).trim());
  if (filters.issueType) query.set("issueType", String(filters.issueType).trim());
  const res = await fetch(
    `${FUNCTION_BASE_URL}/api/scans/${encodeURIComponent(scanId)}/fix-records?${query.toString()}`,
    { credentials: "same-origin" }
  );
  const body = await readJsonResponse(res, "getFixRecords");
  return normalizeFixRecords(body);
}

export function startFixExport(scanId, filters = {}) {
  return fetch(
    `${FUNCTION_BASE_URL}/api/scans/${encodeURIComponent(scanId)}/fix-export`,
    {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        module: String(filters.module || "").trim(),
        q: String(filters.q || "").trim(),
        owners: Array.isArray(filters.owners) ? filters.owners : [],
        severity: String(filters.severity || "").trim(),
        issueType: String(filters.issueType || "").trim(),
      }),
    }
  ).then((res) => readJsonResponse(res, "startFixExport"));
}

export function getFixExport(scanId, exportId) {
  return fetch(
    `${FUNCTION_BASE_URL}/api/scans/${encodeURIComponent(scanId)}/fix-export/${encodeURIComponent(exportId)}`,
    { credentials: "same-origin" }
  ).then((res) => readJsonResponse(res, "getFixExport"));
}

export function fixExportFileUrl(scanId, exportId) {
  return `${FUNCTION_BASE_URL}/api/scans/${encodeURIComponent(scanId)}/fix-export/${encodeURIComponent(exportId)}/file`;
}

function filenameFromDisposition(disposition, exportId) {
  const match = /filename="([^"]+)"/i.exec(String(disposition || ""));
  return match?.[1] || `fix-export-${exportId}.xlsx`;
}

export async function downloadFixExportFile(scanId, exportId) {
  const res = await fetch(fixExportFileUrl(scanId, exportId), {
    credentials: "same-origin",
  });
  if (!res.ok) {
    let body = null;
    try {
      body = await res.json();
    } catch {
      body = null;
    }
    const error = new Error(body?.error?.message || "Fix export could not be downloaded");
    error.code = body?.error?.code || "FIX_EXPORT_READ_FAILED";
    error.status = res.status;
    throw error;
  }
  const blob = await res.blob();
  const filename = filenameFromDisposition(
    res.headers.get("Content-Disposition"),
    exportId
  );
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
  return filename;
}

export function estimateScan(scopeConfig, accessibleModules = []) {
  return buildScanEstimate(scopeConfig, accessibleModules);
}
