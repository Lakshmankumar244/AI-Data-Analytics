"""Load pipeline_tasks and validate Salesforce scan ownership.

Uses the existing pipeline_tasks and scan_jobs tables. Does not create a
Salesforce-specific task table and does not write scan or task state.
"""

from shared.datastore import foreign_row_id, query_one as _query_one

SALESFORCE_TASK_TYPE = "ORCHESTRATE_SALESFORCE_SCAN"
ZOHO_TASK_TYPE = "ORCHESTRATE_SCAN"
SALESFORCE_CRM_PROVIDER = "salesforce"
SALESFORCE_CONNECTIONS_TABLE = "salesforce_connections"


class SalesforceWorkerError(ValueError):
    """Controlled Job Function rejection (malformed or unsupported input)."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def scan_crm_provider(scan_row):
    """Return the CRM that owns scan_jobs.connection_row_id. Missing means Zoho."""
    value = str((scan_row or {}).get("crm_provider") or "zoho").strip().lower()
    return value or "zoho"


def _escape(value):
    return str(value).replace("'", "''")


def _digit_row_id(value):
    row_id = str(foreign_row_id(value) or "").strip()
    return row_id if row_id.isdigit() else ""


def find_pipeline_task(zcql, task_id):
    safe_task_id = _escape(task_id)
    return _query_one(
        zcql,
        f"select * from pipeline_tasks where task_id = '{safe_task_id}' limit 1",
        "pipeline_tasks",
    )


def find_scan_by_row_id(zcql, scan_row_id):
    row_id = _digit_row_id(scan_row_id)
    if not row_id:
        return None
    return _query_one(
        zcql,
        f"select * from scan_jobs where ROWID = {row_id} limit 1",
        "scan_jobs",
    )


def find_persisted_salesforce_connection(zcql, scan_row):
    """Load the scan's Salesforce connection. Never query zoho_connections."""
    if scan_crm_provider(scan_row) != SALESFORCE_CRM_PROVIDER:
        return None
    connection_row_id = _digit_row_id((scan_row or {}).get("connection_row_id"))
    if not connection_row_id:
        return None
    return _query_one(
        zcql,
        f"select * from {SALESFORCE_CONNECTIONS_TABLE} where "
        f"ROWID = {connection_row_id} limit 1",
        SALESFORCE_CONNECTIONS_TABLE,
    )


def resolve_salesforce_task(zcql, task_id):
    """Return safe identifiers for a Salesforce-owned pipeline task."""
    if not isinstance(task_id, str) or not task_id.strip():
        raise SalesforceWorkerError("TASK_ID_REQUIRED", "taskId is required")

    task_row = find_pipeline_task(zcql, task_id.strip())
    if not task_row:
        raise SalesforceWorkerError("TASK_NOT_FOUND", "Pipeline task was not found")

    task_type = str(task_row.get("task_type") or "").strip()
    if task_type != SALESFORCE_TASK_TYPE:
        raise SalesforceWorkerError(
            "WRONG_TASK_TYPE",
            f"Unsupported task type {task_type or 'missing'}",
        )

    scan_row = find_scan_by_row_id(zcql, task_row.get("scan_row_id"))
    if not scan_row:
        raise SalesforceWorkerError("SCAN_NOT_FOUND", "Scan was not found")

    provider = scan_crm_provider(scan_row)
    if provider != SALESFORCE_CRM_PROVIDER:
        raise SalesforceWorkerError(
            "WRONG_CRM_PROVIDER",
            "Salesforce worker requires a Salesforce scan",
        )

    connection_row = find_persisted_salesforce_connection(zcql, scan_row)
    scan_connection_id = _digit_row_id(scan_row.get("connection_row_id"))
    stored_connection_id = _digit_row_id((connection_row or {}).get("ROWID"))
    if (
        not connection_row
        or not stored_connection_id
        or scan_connection_id != stored_connection_id
    ):
        raise SalesforceWorkerError(
            "SCAN_NOT_OWNED",
            "Salesforce scan ownership mismatch",
        )

    return {
        "taskId": str(task_row.get("task_id") or task_id.strip()),
        "scanId": str(scan_row.get("scan_id") or ""),
        "crmProvider": provider,
        "taskType": task_type,
        "task": task_row,
        "scan": scan_row,
        "connection": connection_row,
    }


def find_scan_modules(zcql, scan_row_id):
    row_id = _digit_row_id(scan_row_id)
    if not row_id:
        return []
    results = zcql.execute_query(
        f"select * from scan_module_runs where scan_row_id = {row_id}"
    )
    rows = [item["scan_module_runs"] for item in results]
    return sorted(rows, key=lambda row: int(row.get("ROWID") or 0))


def find_bulk_jobs_for_module(zcql, module_row_id):
    row_id = _digit_row_id(module_row_id)
    if not row_id:
        return []
    results = zcql.execute_query(
        "select * from bulk_read_jobs where "
        f"scan_module_row_id = {row_id}"
    )
    return [item["bulk_read_jobs"] for item in results]
