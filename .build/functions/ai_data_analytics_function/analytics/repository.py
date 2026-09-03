"""Read-only Catalyst Data Store queries for analytics APIs."""

from common.core import foreign_row_id


def _rows(zcql, query, table_name):
    return [item[table_name] for item in zcql.execute_query(query)]


def find_owned_scan(zcql, scan_id, user_id):
    safe_scan_id = scan_id.replace("'", "''")
    scan_rows = _rows(
        zcql,
        f"select * from scan_jobs where scan_id = '{safe_scan_id}' limit 1",
        "scan_jobs",
    )
    if not scan_rows:
        return None

    safe_user_id = user_id.replace("'", "''")
    connection_rows = _rows(
        zcql,
        f"select ROWID from zoho_connections where user_id = '{safe_user_id}'",
        "zoho_connections",
    )
    if not connection_rows:
        return None

    scan_row = scan_rows[0]
    owned_connection_ids = {str(row["ROWID"]) for row in connection_rows}
    if str(foreign_row_id(scan_row.get("connection_row_id"))) not in owned_connection_ids:
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
