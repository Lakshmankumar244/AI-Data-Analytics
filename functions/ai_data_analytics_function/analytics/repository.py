"""Read-only Catalyst Data Store queries for analytics APIs."""

from common.core import foreign_row_id
from connections.repository import scan_crm_provider


def _rows(zcql, query, table_name):
    return [item[table_name] for item in zcql.execute_query(query)]


def find_owned_scan(zcql, scan_id, user_id):
    """Return a scan the caller may access via dual-read connection authorization."""
    from installations.authorization import (
        find_accessible_salesforce_connection,
        find_accessible_zoho_connection,
    )

    safe_scan_id = scan_id.replace("'", "''")
    scan_rows = _rows(
        zcql,
        f"select * from scan_jobs where scan_id = '{safe_scan_id}' limit 1",
        "scan_jobs",
    )
    if not scan_rows:
        return None

    scan_row = scan_rows[0]
    connection_row_id = foreign_row_id(scan_row.get("connection_row_id"))
    if scan_crm_provider(scan_row) == "salesforce":
        accessible = find_accessible_salesforce_connection(
            zcql, connection_row_id, user_id
        )
    else:
        accessible = find_accessible_zoho_connection(
            zcql, connection_row_id, user_id
        )
    if not accessible:
        return None
    return scan_row


def find_module_runs(zcql, scan_row_id):
    return _rows(
        zcql,
        f"select * from scan_module_runs where scan_row_id = {int(scan_row_id)}",
        "scan_module_runs",
    )


def find_bulk_jobs(zcql, module_row_id):
    return _rows(
        zcql,
        "select * from bulk_read_jobs where "
        f"scan_module_row_id = {int(module_row_id)}",
        "bulk_read_jobs",
    )


def find_processing_batches(zcql, bulk_job_row_id):
    return _rows(
        zcql,
        "select * from processing_batches where "
        f"bulk_job_row_id = {int(bulk_job_row_id)}",
        "processing_batches",
    )


def find_pipeline_tasks(zcql, scan_row_id):
    return _rows(
        zcql,
        f"select * from pipeline_tasks where scan_row_id = {int(scan_row_id)}",
        "pipeline_tasks",
    )


def find_analytics_results(zcql, scan_row_id):
    return _rows(
        zcql,
        f"select * from analytics_results where scan_row_id = {int(scan_row_id)}",
        "analytics_results",
    )


def find_fix_record_findings(zcql, conditions, fetch_limit):
    """Page defective v5 findings for Fix. Caller supplies the full WHERE list."""
    if not conditions:
        raise ValueError("Fix findings query requires conditions")
    limit = int(fetch_limit)
    if limit < 1:
        raise ValueError("Fix findings fetch limit is invalid")
    return _rows(
        zcql,
        "select ROWID,crm_record_id,display_name,owner_key,highest_severity,"
        "processing_batch_row_id,jsonl_line,issue_type_keys,module_api_name,"
        "schema_version,issue_count from record_quality_findings where "
        + " and ".join(conditions)
        + f" order by ROWID asc limit 0,{limit}",
        "record_quality_findings",
    )


def find_processing_batches_by_row_ids(zcql, row_ids):
    ids = []
    seen = set()
    for value in row_ids:
        row_id = str(foreign_row_id(value) or "")
        if not row_id.isdigit() or row_id in seen:
            continue
        seen.add(row_id)
        ids.append(row_id)
    if not ids:
        return []
    return _rows(
        zcql,
        "select ROWID,batch_number from processing_batches where "
        f"ROWID in ({','.join(ids)})",
        "processing_batches",
    )
