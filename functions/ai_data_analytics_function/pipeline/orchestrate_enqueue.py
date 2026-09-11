"""Idempotent ORCHESTRATE_SCAN job submission for the existing worker pool."""

import logging
import os
import time
import uuid

from pipeline.shared import (
    catalyst_datetime_now,
    catalyst_error_details,
    canonical_hash,
    job_identifier,
)

LOGGER = logging.getLogger(__name__)

ORCHESTRATE_TASK_TYPE = "ORCHESTRATE_SCAN"
ORCHESTRATE_VERSION = "orchestrate-v1"
ACTIVE_ORCHESTRATE_STATES = {"PLANNED", "QUEUED", "RUNNING"}


def orchestrate_task_key(scan_id):
    return canonical_hash(
        {
            "task_type": ORCHESTRATE_TASK_TYPE,
            "scan_id": scan_id,
            "version": ORCHESTRATE_VERSION,
        }
    )


def _worker_target():
    pool_name = os.environ.get("ANALYTICS_WORKER_JOB_POOL_NAME", "")
    function_name = os.environ.get("ANALYTICS_WORKER_FUNCTION_NAME", "")
    return pool_name, function_name


def find_orchestrate_task(zcql, scan_id):
    task_key = orchestrate_task_key(scan_id)
    results = zcql.execute_query(
        f"select * from pipeline_tasks where task_key = '{task_key}' limit 1"
    )
    if not results:
        return None
    return results[0]["pipeline_tasks"]


def ensure_orchestrate_task(datastore, zcql, scan_row):
    """Return the durable ORCHESTRATE_SCAN row for this scan, creating it if needed."""
    scan_id = scan_row.get("scan_id")
    task_row = find_orchestrate_task(zcql, scan_id)
    task_table = datastore.table("pipeline_tasks")
    if task_row:
        return task_row
    return task_table.insert_row(
        {
            "task_id": f"task_{uuid.uuid4().hex}",
            "task_key": orchestrate_task_key(scan_id),
            "scan_row_id": scan_row["ROWID"],
            "task_type": ORCHESTRATE_TASK_TYPE,
            "status": "PLANNED",
            "attempt_count": 0,
        }
    )


def submit_orchestrate_job(app, task_id, delay_seconds=0):
    """Submit the existing worker; delay uses a one-time Cron when required."""
    pool_name, function_name = _worker_target()
    if not pool_name or not function_name:
        raise RuntimeError("ANALYTICS_WORKER_NOT_CONFIGURED")

    job_name = f"ada_{canonical_hash(f'{task_id}:{time.time_ns()}:{delay_seconds}')[:16]}"
    job_payload = {
        "job_name": job_name,
        "jobpool_name": pool_name,
        "target_type": "Function",
        "target_name": function_name,
        "params": {"taskId": task_id},
    }
    delay = max(0, int(delay_seconds or 0))
    if delay > 0:
        try:
            return _submit_delayed_job(app, job_payload, delay), True
        except Exception:
            LOGGER.exception(
                "ORCHESTRATE_SCAN delayed enqueue fell back to immediate submit task_id=%s delay=%s",
                task_id,
                delay,
            )
    job_response = app.job_scheduling().job.submit_job(job_payload)
    return job_response, False


def _submit_delayed_job(app, job_payload, delay_seconds):
    execution_at = int(time.time()) + delay_seconds
    scheduling = app.job_scheduling()
    cron_service = getattr(scheduling, "CRON", None) or getattr(scheduling, "cron", None)
    if cron_service is None:
        raise RuntimeError("Catalyst Cron API is unavailable")
    return cron_service.create(
        {
            "cron_name": job_payload["job_name"],
            "description": "ORCHESTRATE_SCAN retry tick",
            "cron_status": True,
            "cron_type": "OneTime",
            "cron_detail": {"time_of_execution": execution_at},
            "job_meta": {
                "job_name": job_payload["job_name"],
                "target_type": job_payload["target_type"],
                "target_name": job_payload["target_name"],
                "jobpool_name": job_payload["jobpool_name"],
                "params": job_payload["params"],
            },
        }
    )


def enqueue_orchestrate_scan(app, datastore, scan_row, delay_seconds=0):
    """Queue ORCHESTRATE_SCAN unless a tick is already active or outcome is unknown."""
    zcql = app.zcql()
    task_row = ensure_orchestrate_task(datastore, zcql, scan_row)
    status = str(task_row.get("status") or "")
    if status in {"QUEUED", "RUNNING"}:
        return {
            "ok": True,
            "alreadyActive": True,
            "submitted": False,
            "task": task_row,
        }
    if status == "OUTCOME_UNKNOWN":
        return {
            "ok": False,
            "code": "WORKER_ENQUEUE_OUTCOME_UNKNOWN",
            "task": task_row,
        }
    if status == "SUCCEEDED" and str(scan_row.get("status") or "") == "COMPLETED":
        return {
            "ok": True,
            "alreadyComplete": True,
            "submitted": False,
            "task": task_row,
        }
    if status not in {"PLANNED", "PAUSED_RETRYABLE", "SUCCEEDED"}:
        return {
            "ok": False,
            "code": "PIPELINE_TASK_STATE_CONFLICT",
            "task": task_row,
        }

    pool_name, function_name = _worker_target()
    if not pool_name or not function_name:
        return {
            "ok": False,
            "code": "ANALYTICS_WORKER_NOT_CONFIGURED",
            "task": task_row,
        }

    task_table = datastore.table("pipeline_tasks")
    task_table.update_row(
        {
            "ROWID": task_row["ROWID"],
            "status": "QUEUED",
            "enqueued_at": catalyst_datetime_now(),
            "controlled_error_code": "",
        }
    )
    try:
        job_response, delayed = submit_orchestrate_job(
            app, task_row["task_id"], delay_seconds=delay_seconds
        )
        catalyst_job_id = job_identifier(job_response)
    except Exception as exc:  # noqa: BLE001 - submission outcome may be ambiguous
        catalyst_error = catalyst_error_details(exc)
        LOGGER.exception(
            "ORCHESTRATE_SCAN enqueue outcome unknown task_id=%s error=%s",
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
            return {
                "ok": False,
                "code": "WORKER_ENQUEUE_REJECTED",
                "task": task_row,
                "details": catalyst_error,
            }
        task_table.update_row(
            {
                "ROWID": task_row["ROWID"],
                "status": "OUTCOME_UNKNOWN",
                "controlled_error_code": "WORKER_ENQUEUE_OUTCOME_UNKNOWN",
            }
        )
        return {
            "ok": False,
            "code": "WORKER_ENQUEUE_OUTCOME_UNKNOWN",
            "task": task_row,
            "details": catalyst_error,
        }

    if catalyst_job_id:
        try:
            task_table.update_row(
                {
                    "ROWID": task_row["ROWID"],
                    "catalyst_job_id": catalyst_job_id,
                }
            )
        except Exception:
            LOGGER.exception(
                "Could not persist ORCHESTRATE_SCAN job id task_id=%s",
                task_row["task_id"],
            )
    return {
        "ok": True,
        "alreadyActive": False,
        "submitted": True,
        "delayed": delayed,
        "delaySeconds": int(delay_seconds or 0),
        "task": {**task_row, "status": "QUEUED"},
        "workerJobId": catalyst_job_id,
    }
