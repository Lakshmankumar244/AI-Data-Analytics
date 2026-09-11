"""Create and enqueue idempotent export-processing tasks."""

import logging
import os
import uuid

import zcatalyst_sdk

from connections.repository import find_scan_connection

from pipeline.shared import (
    catalyst_datetime_now,
    catalyst_error_details,
    canonical_hash,
    foreign_row_id,
    get_current_user_id,
    job_identifier,
    json_response,
)
from common.profiler import profile_stage

LOGGER = logging.getLogger(__name__)

TASK_TYPE_PROCESS_BATCHES = "PROCESS_BATCHES"


def enqueue_process_batches(request, datastore, scan_id, bulk_job_id):
    """Create and enqueue one idempotent PROCESS_BATCHES task."""
    zcql = zcatalyst_sdk.initialize().zcql()
    safe_scan_id = scan_id.replace("'", "''")
    scan_results = zcql.execute_query(
        f"select * from scan_jobs where scan_id = '{safe_scan_id}' limit 1"
    )
    if not scan_results:
        return json_response(
            {"error": {"code": "SCAN_NOT_FOUND", "message": "Scan was not found"}},
            404,
        )
    scan_row = scan_results[0]["scan_jobs"]

    user_id = get_current_user_id(request)
    connection_row = find_scan_connection(zcql, user_id, scan_row)
    if not connection_row:
        return json_response(
            {
                "error": {
                    "code": "ZOHO_CONNECTION_REQUIRED",
                    "message": "Reconnect Zoho CRM",
                }
            },
            409,
        )
    safe_bulk_job_id = bulk_job_id.replace("'", "''")
    bulk_results = zcql.execute_query(
        "select * from bulk_read_jobs where "
        f"bulk_job_id = '{safe_bulk_job_id}' limit 1"
    )
    if not bulk_results:
        return json_response(
            {
                "error": {
                    "code": "BULK_JOB_NOT_FOUND",
                    "message": "Bulk Read job was not found",
                }
            },
            404,
        )
    bulk_row = bulk_results[0]["bulk_read_jobs"]

    module_row_id = str(foreign_row_id(bulk_row.get("scan_module_row_id")))
    if not module_row_id.isdigit():
        return json_response(
            {
                "error": {
                    "code": "INVALID_BULK_JOB_LINK",
                    "message": "Bulk Read job has an invalid module link",
                }
            },
            500,
        )
    module_results = zcql.execute_query(
        f"select * from scan_module_runs where ROWID = {module_row_id} limit 1"
    )
    if not module_results:
        return json_response(
            {
                "error": {
                    "code": "BULK_JOB_NOT_FOUND",
                    "message": "Bulk Read job was not found",
                }
            },
            404,
        )
    module_row = module_results[0]["scan_module_runs"]
    if str(foreign_row_id(module_row.get("scan_row_id"))) != str(scan_row["ROWID"]):
        return json_response(
            {
                "error": {
                    "code": "BULK_JOB_NOT_FOUND",
                    "message": "Bulk Read job was not found",
                }
            },
            404,
        )

    if bulk_row.get("status") == "PROCESSED":
        return json_response(
            {
                "scanId": scan_id,
                "bulkJobId": bulk_job_id,
                "module": module_row["module_api_name"],
                "status": "PROCESSED",
                "alreadyProcessed": True,
                "workerJobSubmitted": False,
                "zohoApiCalls": 0,
                "zohoCreditsConsumed": 0,
            }
        )
    if bulk_row.get("status") not in {"PROCESSING_PLANNED", "PROCESSING"}:
        return json_response(
            {
                "error": {
                    "code": "BULK_JOB_STATE_CONFLICT",
                    "message": (
                        "Batches cannot be processed from state "
                        f"{bulk_row.get('status')}"
                    ),
                }
            },
            409,
        )

    task_key = canonical_hash(
        {
            "task_type": TASK_TYPE_PROCESS_BATCHES,
            "bulk_job_id": bulk_job_id,
            "source_file_checksum": bulk_row.get("source_file_checksum"),
            "aggregate_schema_version": "quality-aggregate-v1",
            "rule_version": "quality-rules-v1",
        }
    )
    task_results = zcql.execute_query(
        f"select * from pipeline_tasks where task_key = '{task_key}' limit 1"
    )
    task_table = datastore.table("pipeline_tasks")
    if task_results:
        task_row = task_results[0]["pipeline_tasks"]
        task_status = task_row.get("status")
        if task_status == "SUCCEEDED":
            return json_response(
                {
                    "scanId": scan_id,
                    "bulkJobId": bulk_job_id,
                    "taskId": task_row["task_id"],
                    "status": "PROCESSED",
                    "taskStatus": "SUCCEEDED",
                    "alreadyProcessed": True,
                    "workerJobSubmitted": False,
                    "zohoApiCalls": 0,
                    "zohoCreditsConsumed": 0,
                }
            )
        if task_status in {"QUEUED", "RUNNING"}:
            return json_response(
                {
                    "scanId": scan_id,
                    "bulkJobId": bulk_job_id,
                    "taskId": task_row["task_id"],
                    "taskStatus": task_status,
                    "workerJobId": task_row.get("catalyst_job_id"),
                    "alreadyQueued": True,
                    "workerJobSubmitted": False,
                    "zohoApiCalls": 0,
                    "zohoCreditsConsumed": 0,
                },
                202,
            )
        if task_status == "OUTCOME_UNKNOWN":
            return json_response(
                {
                    "error": {
                        "code": "WORKER_ENQUEUE_OUTCOME_UNKNOWN",
                        "message": "Inspect the Job Pool before retrying this task",
                    },
                    "taskId": task_row["task_id"],
                },
                409,
            )
        if task_status not in {"PLANNED", "PAUSED_RETRYABLE"}:
            return json_response(
                {
                    "error": {
                        "code": "PIPELINE_TASK_STATE_CONFLICT",
                        "message": f"Task cannot be queued from state {task_status}",
                    },
                    "taskId": task_row["task_id"],
                },
                409,
            )
    else:
        task_row = task_table.insert_row(
            {
                "task_id": f"task_{uuid.uuid4().hex}",
                "task_key": task_key,
                "scan_row_id": scan_row["ROWID"],
                "scan_module_row_id": module_row["ROWID"],
                "bulk_job_row_id": bulk_row["ROWID"],
                "task_type": TASK_TYPE_PROCESS_BATCHES,
                "status": "PLANNED",
                "attempt_count": 0,
            }
        )

    pool_name = os.environ.get("ANALYTICS_WORKER_JOB_POOL_NAME", "")
    function_name = os.environ.get("ANALYTICS_WORKER_FUNCTION_NAME", "")
    if not pool_name or not function_name:
        return json_response(
            {
                "error": {
                    "code": "ANALYTICS_WORKER_NOT_CONFIGURED",
                    "message": "The analytics worker Job Pool is not configured",
                },
                "taskId": task_row["task_id"],
            },
            500,
        )

    job_name = f"ada_{canonical_hash(task_row['task_id'])[:16]}"
    task_table.update_row(
        {
            "ROWID": task_row["ROWID"],
            "status": "QUEUED",
            "enqueued_at": catalyst_datetime_now(),
            "controlled_error_code": "",
        }
    )
    try:
        with profile_stage(
            "orchestration",
            "enqueue_process_batches",
            scanId=scan_id,
            bulkJobId=bulk_job_id,
            taskId=task_row["task_id"],
        ):
            job_response = zcatalyst_sdk.initialize().job_scheduling().job.submit_job(
                {
                    "job_name": job_name,
                    "jobpool_name": pool_name,
                    "target_type": "Function",
                    "target_name": function_name,
                    "params": {"taskId": task_row["task_id"]},
                }
            )
            catalyst_job_id = job_identifier(job_response)
    except Exception as exc:  # noqa: BLE001 - submission outcome may be ambiguous
        catalyst_error = catalyst_error_details(exc)
        LOGGER.exception(
            "Processing worker enqueue failed task_id=%s error=%s",
            task_row["task_id"],
            catalyst_error,
        )
        try:
            status_code = int(catalyst_error.get("status_code") or 0)
        except (TypeError, ValueError):
            status_code = 0
        if 400 <= status_code < 500:
            task_table.update_row(
                {
                    "ROWID": task_row["ROWID"],
                    "status": "PAUSED_RETRYABLE",
                    "controlled_error_code": "WORKER_ENQUEUE_REJECTED",
                }
            )
            return json_response(
                {
                    "error": {
                        "code": "WORKER_ENQUEUE_REJECTED",
                        "message": "Catalyst rejected the worker job submission",
                    },
                    "taskId": task_row["task_id"],
                    "details": catalyst_error,
                    "zohoApiCalls": 0,
                    "zohoCreditsConsumed": 0,
                },
                status_code,
            )
        return json_response(
            {
                "error": {
                    "code": "WORKER_ENQUEUE_OUTCOME_UNKNOWN",
                    "message": (
                        "Inspect the Job Pool before retrying; the task remains QUEUED"
                    ),
                },
                "taskId": task_row["task_id"],
                "details": catalyst_error,
                "zohoApiCalls": 0,
                "zohoCreditsConsumed": 0,
            },
            502,
        )

    if catalyst_job_id:
        try:
            task_table.update_row(
                {"ROWID": task_row["ROWID"], "catalyst_job_id": catalyst_job_id}
            )
        except Exception:
            LOGGER.exception(
                "Worker job %s submitted but task ID persistence failed",
                catalyst_job_id,
            )
            return json_response(
                {
                    "error": {
                        "code": "WORKER_JOB_ID_PERSIST_FAILED",
                        "message": "The worker job was submitted but its ID was not stored",
                    },
                    "taskId": task_row["task_id"],
                    "workerJobId": catalyst_job_id,
                    "zohoApiCalls": 0,
                    "zohoCreditsConsumed": 0,
                },
                500,
            )

    return json_response(
        {
            "scanId": scan_id,
            "bulkJobId": bulk_job_id,
            "module": module_row["module_api_name"],
            "taskId": task_row["task_id"],
            "taskStatus": "QUEUED",
            "workerJobId": catalyst_job_id,
            "workerJobSubmitted": True,
            "zohoApiCalls": 0,
            "zohoCreditsConsumed": 0,
        },
        202,
    )
