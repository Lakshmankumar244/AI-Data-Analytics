"""Read-only HTTP routes for scan progress and aggregate results."""

import logging

import zcatalyst_sdk

from analytics.repository import (
    find_analytics_results,
    find_bulk_jobs,
    find_module_runs,
    find_owned_scan,
    find_pipeline_tasks,
    find_processing_batches,
)
from analytics.service import StoredAnalyticsError, build_results, build_status
from common.core import AuthenticationRequired, get_current_user_id, json_response


LOGGER = logging.getLogger(__name__)


def _owned_scan(request, scan_id):
    zcql = zcatalyst_sdk.initialize().zcql()
    return zcql, find_owned_scan(zcql, scan_id, get_current_user_id(request))


def get_scan_status(request, datastore, scan_id):
    """Return durable scan, module, bulk, batch, and task progress."""
    del datastore  # The repository uses ZCQL for filtered, read-only queries.
    try:
        zcql, scan_row = _owned_scan(request, scan_id)
        if not scan_row:
            return json_response(
                {"error": {"code": "SCAN_NOT_FOUND", "message": "Scan was not found"}},
                404,
            )

        module_rows = find_module_runs(zcql, scan_row["ROWID"])
        bulk_jobs_by_module = {}
        batches_by_bulk = {}
        for module_row in module_rows:
            module_key = str(module_row["ROWID"])
            bulk_jobs = find_bulk_jobs(zcql, module_row["ROWID"])
            bulk_jobs_by_module[module_key] = bulk_jobs
            for bulk_job in bulk_jobs:
                batches_by_bulk[str(bulk_job["ROWID"])] = find_processing_batches(
                    zcql, bulk_job["ROWID"]
                )
        tasks = find_pipeline_tasks(zcql, scan_row["ROWID"])
        return json_response(
            build_status(
                scan_row,
                module_rows,
                bulk_jobs_by_module,
                batches_by_bulk,
                tasks,
            )
        )
    except AuthenticationRequired:
        raise
    except Exception as exc:  # noqa: BLE001 - return a controlled read failure
        LOGGER.exception("Could not read scan status scan_id=%s: %s", scan_id, exc)
        return json_response(
            {
                "error": {
                    "code": "SCAN_STATUS_READ_FAILED",
                    "message": "Scan status could not be read",
                }
            },
            500,
        )


def get_scan_results(request, datastore, scan_id):
    """Return computed module aggregates without exposing CRM records."""
    del datastore
    try:
        zcql, scan_row = _owned_scan(request, scan_id)
        if not scan_row:
            return json_response(
                {"error": {"code": "SCAN_NOT_FOUND", "message": "Scan was not found"}},
                404,
            )
        result_rows = find_analytics_results(zcql, scan_row["ROWID"])
        return json_response(build_results(scan_row, result_rows))
    except StoredAnalyticsError as exc:
        LOGGER.exception("Stored analytics is invalid scan_id=%s: %s", scan_id, exc)
        return json_response(
            {
                "error": {
                    "code": "STORED_ANALYTICS_INVALID",
                    "message": "Stored analytics results are invalid",
                }
            },
            500,
        )
    except AuthenticationRequired:
        raise
    except Exception as exc:  # noqa: BLE001 - return a controlled read failure
        LOGGER.exception("Could not read scan results scan_id=%s: %s", scan_id, exc)
        return json_response(
            {
                "error": {
                    "code": "SCAN_RESULTS_READ_FAILED",
                    "message": "Scan results could not be read",
                }
            },
            500,
        )
