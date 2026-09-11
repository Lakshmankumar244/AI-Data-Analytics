"""Load scan pipeline state without a request-scoped user."""


def _rows(zcql, query, table_name):
    return [item[table_name] for item in zcql.execute_query(query)]


def load_scan_state(zcql, scan_id):
    safe_scan_id = str(scan_id).replace("'", "''")
    scan_rows = _rows(
        zcql,
        f"select * from scan_jobs where scan_id = '{safe_scan_id}' limit 1",
        "scan_jobs",
    )
    if not scan_rows:
        return None
    scan_row = scan_rows[0]
    modules = _rows(
        zcql,
        f"select * from scan_module_runs where scan_row_id = {int(scan_row['ROWID'])}",
        "scan_module_runs",
    )
    bulk_jobs_by_module = {
        str(module["ROWID"]): _rows(
            zcql,
            "select * from bulk_read_jobs where "
            f"scan_module_row_id = {int(module['ROWID'])}",
            "bulk_read_jobs",
        )
        for module in modules
    }
    tasks = _rows(
        zcql,
        f"select * from pipeline_tasks where scan_row_id = {int(scan_row['ROWID'])}",
        "pipeline_tasks",
    )
    return {
        "scan": scan_row,
        "modules": modules,
        "bulk_jobs_by_module": bulk_jobs_by_module,
        "tasks": tasks,
    }
