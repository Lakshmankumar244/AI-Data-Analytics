const ISSUE_TYPE_MESSAGES = {
  MISSING_VALUE: "Missing value",
  INVALID_EMAIL: "Invalid email",
  INVALID_PHONE: "Invalid phone",
  INVALID_URL: "Invalid URL",
  INVALID_NUMBER: "Invalid number",
  INVALID_DATETIME: "Invalid date/time",
};

const MESSAGE_CODE_MESSAGES = {
  INVALID_EMAIL_FORMAT: "Invalid email",
  INVALID_PHONE_FORMAT: "Invalid phone",
  INVALID_URL_FORMAT: "Invalid URL",
  INVALID_NUMBER_FORMAT: "Invalid number",
  INVALID_DATETIME_FORMAT: "Invalid date/time",
  SYSTEM_MANDATORY_VALUE_MISSING: "Missing value",
  UNIQUE_FIELD_VALUE_MISSING: "Missing value",
  BUSINESS_CRITICAL_VALUE_MISSING: "Missing value",
  OPTIONAL_VALUE_MISSING: "Missing value",
  LEGACY_ANALYSIS_VALUE_MISSING: "Missing value",
};

export const FIX_PAGE_SIZE = 20;
export const FIX_INDEX_UNAVAILABLE = "FIX_INDEX_UNAVAILABLE";

export const ISSUE_TYPE_FILTERS = [
  { id: "", label: "All issue types" },
  { id: "MISSING_VALUE", label: "Missing value" },
  { id: "INVALID_EMAIL", label: "Invalid email" },
  { id: "INVALID_PHONE", label: "Invalid phone" },
  { id: "INVALID_URL", label: "Invalid URL" },
  { id: "INVALID_NUMBER", label: "Invalid number" },
  { id: "INVALID_DATETIME", label: "Invalid date/time" },
];

export const SEVERITY_FILTERS = [
  { id: "", label: "All severities" },
  { id: "CRITICAL", label: "Critical" },
  { id: "HIGH", label: "High" },
  { id: "MEDIUM", label: "Medium" },
  { id: "LOW", label: "Low" },
];

export function cellValue(cells, apiName) {
  if (!cells || typeof cells !== "object") return "";
  const value = cells[apiName];
  if (value == null) return "";
  return String(value);
}

export function issueMessage(issue = {}) {
  const code = String(issue.messageCode || "").trim();
  if (MESSAGE_CODE_MESSAGES[code]) return MESSAGE_CODE_MESSAGES[code];
  const type = String(issue.issueType || "").trim();
  if (ISSUE_TYPE_MESSAGES[type]) return ISSUE_TYPE_MESSAGES[type];
  const label = String(issue.fieldLabel || issue.fieldApiName || "").trim();
  if (type) return label ? `${type.replaceAll("_", " ").toLowerCase()} · ${label}` : type;
  return "Quality issue detected";
}

function normalizeIssue(issue) {
  if (!issue || typeof issue !== "object") return null;
  const fieldApiName = String(issue.fieldApiName || "").trim();
  if (!fieldApiName) return null;
  return {
    fieldApiName,
    fieldLabel: String(issue.fieldLabel || fieldApiName).trim() || fieldApiName,
    issueType: String(issue.issueType || "").trim(),
    severity: String(issue.severity || "").trim().toUpperCase(),
    messageCode: String(issue.messageCode || "").trim(),
    message: issueMessage(issue),
  };
}

function normalizeCells(rawCells) {
  const cells = {};
  if (!rawCells || typeof rawCells !== "object" || Array.isArray(rawCells)) {
    return cells;
  }
  for (const [apiName, value] of Object.entries(rawCells)) {
    const name = String(apiName || "").trim();
    if (!name) continue;
    cells[name] = value == null ? "" : String(value);
  }
  return cells;
}

function issuesByField(issues) {
  const grouped = {};
  for (const issue of issues) {
    const list = grouped[issue.fieldApiName] ?? [];
    list.push(issue);
    grouped[issue.fieldApiName] = list;
  }
  return grouped;
}

function normalizeRow(row) {
  const source = row && typeof row === "object" ? row : {};
  const cells = normalizeCells(source.cells);
  const issues = (Array.isArray(source.issues) ? source.issues : [])
    .map(normalizeIssue)
    .filter(Boolean);
  return {
    crmRecordId: String(source.crmRecordId || "").trim(),
    displayName: String(source.displayName || "").trim(),
    ownerKey: String(source.ownerKey || ""),
    cells,
    issues,
    issuesByField: issuesByField(issues),
  };
}

function normalizeColumns(columns) {
  if (!Array.isArray(columns)) return [];
  const seen = new Set();
  const normalized = [];
  for (const column of columns) {
    const apiName = String(column?.apiName || "").trim();
    if (!apiName || seen.has(apiName)) continue;
    seen.add(apiName);
    normalized.push({
      apiName,
      label: String(column.label || apiName).trim() || apiName,
    });
  }
  return normalized;
}

export function normalizeFixRecords(payload) {
  const source = payload && typeof payload === "object" ? payload : {};
  const kpis = source.kpis && typeof source.kpis === "object" ? source.kpis : {};
  return {
    scanId: String(source.scanId || ""),
    module: String(source.module || ""),
    measured: source.measured !== false,
    schemaVersion: String(source.schemaVersion || ""),
    pageSize: Number(source.pageSize) || FIX_PAGE_SIZE,
    nextCursor: source.nextCursor == null || source.nextCursor === ""
      ? null
      : String(source.nextCursor),
    hasMore: Boolean(source.hasMore),
    columns: normalizeColumns(source.columns),
    kpis: {
      affectedRecordCount: Number(kpis.affectedRecordCount) || 0,
      issueCount: Number(kpis.issueCount) || 0,
      fixedCount: 0,
    },
    rows: (Array.isArray(source.rows) ? source.rows : []).map(normalizeRow),
  };
}

export function isFixIndexUnavailable(error) {
  return String(error?.code || "") === FIX_INDEX_UNAVAILABLE || Number(error?.status) === 409;
}
