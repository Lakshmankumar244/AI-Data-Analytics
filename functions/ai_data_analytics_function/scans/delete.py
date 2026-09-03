"""Authenticated, conditional deletion of one scan's persisted datastore rows."""

import logging

import zcatalyst_sdk

from analytics.repository import find_owned_scan
from common.core import AuthenticationRequired, get_current_user_id, json_response


LOGGER = logging.getLogger(__name__)
QUERY_PAGE_SIZE = 300
DELETE_BATCH_SIZE = 200
ACTIVE_TASK_STATUSES = frozenset({"QUEUED", "RUNNING", "OUTCOME_UNKNOWN"})


def _rows(zcql, query, table_name):
    return [item[table_name] for item in zcql.execute_query(query)]


def _all_rows(zcql, query_prefix, table_name):
    rows = []
    offset = 0
    while True:
        page = _rows(
            zcql,
            f"{query_prefix} limit {offset},{QUERY_PAGE_SIZE}",
            table_name,
        )
        rows.extend(page)
        if len(page) < QUERY_PAGE_SIZE:
            return rows
        offset += QUERY_PAGE_SIZE


def _delete_rows(datastore, table_name, rows):
    row_ids = [int(row["ROWID"]) for row in rows]
    table = datastore.table(table_name)
    for start in range(0, len(row_ids), DELETE_BATCH_SIZE):
        table.delete_rows(row_ids[start : start + DELETE_BATCH_SIZE])
    return len(row_ids)


def _confirmed_scan_id(request):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("confirmScanId") or "").strip()


def delete_scan(request, datastore, scan_id):
    """Delete one owned scan, descendants first, while retaining its connection."""
    try:
        if _confirmed_scan_id(request) != scan_id:
            return json_response(
                {
                    "error": {
                        "code": "SCAN_DELETE_CONFIRMATION_REQUIRED",
                        "message": "The request body confirmScanId must match the URL scan ID",
                    }
                },
                400,
            )

        app = zcatalyst_sdk.initialize()
        zcql = app.zcql()
        scan_row = find_owned_scan(zcql, scan_id, get_current_user_id(request))
        if not scan_row:
            return json_response(
                {"error": {"code": "SCAN_NOT_FOUND", "message": "Scan was not found"}},
                404,
            )

        scan_row_id = int(scan_row["ROWID"])
        tasks = _all_rows(
            zcql,
            "select * from pipeline_tasks where "
            f"scan_row_id = {scan_row_id} order by ROWID asc",
            "pipeline_tasks",
        )
        active_tasks = [
            row for row in tasks if str(row.get("status") or "").upper() in ACTIVE_TASK_STATUSES
        ]
        if active_tasks:
            return json_response(
                {
                    "error": {
                        "code": "SCAN_DELETE_ACTIVE_TASK",
                        "message": "Wait for or cancel the active Catalyst worker job before deleting this scan",
                    },
                    "activeTaskIds": [str(row.get("task_id") or "") for row in active_tasks],
                },
                409,
            )

        module_rows = _all_rows(
            zcql,
            "select * from scan_module_runs where "
            f"scan_row_id = {scan_row_id} order by ROWID asc",
            "scan_module_runs",
        )
        bulk_rows = []
        for module_row in module_rows:
            bulk_rows.extend(
                _all_rows(
                    zcql,
                    "select * from bulk_read_jobs where "
                    f"scan_module_row_id = {int(module_row['ROWID'])} order by ROWID asc",
                    "bulk_read_jobs",
                )
            )
        batch_rows = []
        for bulk_row in bulk_rows:
            batch_rows.extend(
                _all_rows(
                    zcql,
                    "select * from processing_batches where "
                    f"bulk_job_row_id = {int(bulk_row['ROWID'])} order by ROWID asc",
                    "processing_batches",
                )
            )

        scan_owned_rows = {
            "record_quality_issues": _all_rows(
                zcql,
                "select * from record_quality_issues where "
                f"scan_row_id = {scan_row_id} order by ROWID asc",
                "record_quality_issues",
            ),
            "record_quality_findings": _all_rows(
                zcql,
                "select * from record_quality_findings where "
                f"scan_row_id = {scan_row_id} order by ROWID asc",
                "record_quality_findings",
            ),
            "owner_batch_aggregates": _all_rows(
                zcql,
                "select * from owner_batch_aggregates where "
                f"scan_row_id = {scan_row_id} order by ROWID asc",
                "owner_batch_aggregates",
            ),
            "analytics_results": _all_rows(
                zcql,
                "select * from analytics_results where "
                f"scan_row_id = {scan_row_id} order by ROWID asc",
                "analytics_results",
            ),
            "pipeline_tasks": tasks,
            "processing_batches": batch_rows,
            "bulk_read_jobs": bulk_rows,
            "scan_module_runs": module_rows,
            "scan_jobs": [scan_row],
        }
        source_file_ids = sorted(
            {
                str(row.get("source_file_id"))
                for row in bulk_rows
                if str(row.get("source_file_id") or "").isdigit()
            }
        )

        deleted = {}
        for table_name in (
            "record_quality_issues",
            "record_quality_findings",
            "owner_batch_aggregates",
            "analytics_results",
            "pipeline_tasks",
            "processing_batches",
            "bulk_read_jobs",
            "scan_module_runs",
            "scan_jobs",
        ):
            deleted[table_name] = _delete_rows(
                datastore, table_name, scan_owned_rows[table_name]
            )

        return json_response(
            {
                "scanId": scan_id,
                "deleted": deleted,
                "sourceFileIds": source_file_ids,
                "message": "Scan datastore records were deleted; its Zoho connection was retained",
            }
        )
    except AuthenticationRequired:
        raise
    except Exception as exc:  # noqa: BLE001 - a repeat request safely continues cleanup
        LOGGER.exception("Could not delete scan_id=%s: %s", scan_id, exc)
        return json_response(
            {
                "error": {
                    "code": "SCAN_DELETE_FAILED",
                    "message": "The scan could not be fully deleted; retry the same request",
                }
            },
            500,
        )
