"""Read the durable state needed to choose one safe scan action."""

from analytics.repository import (
    find_bulk_jobs,
    find_module_runs,
    find_owned_scan,
    find_pipeline_tasks,
)


def load_scan_state(zcql, scan_id, user_id):
    """Return an owned scan and its modules, Bulk Read jobs, and worker tasks."""
    scan_row = find_owned_scan(zcql, scan_id, user_id)
    if not scan_row:
        return None

    modules = find_module_runs(zcql, scan_row["ROWID"])
    bulk_jobs_by_module = {
        str(module["ROWID"]): find_bulk_jobs(zcql, module["ROWID"])
        for module in modules
    }
    tasks = find_pipeline_tasks(zcql, scan_row["ROWID"])
    return {
        "scan": scan_row,
        "modules": modules,
        "bulk_jobs_by_module": bulk_jobs_by_module,
        "tasks": tasks,
    }
