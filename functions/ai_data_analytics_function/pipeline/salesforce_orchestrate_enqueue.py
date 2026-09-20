"""Idempotent ORCHESTRATE_SALESFORCE_SCAN job submission.

Targets the Salesforce Job Function and Function Job Pool only.
Does not use the Zoho ANALYTICS_WORKER_* env vars or ORCHESTRATE_SCAN.

QUEUED is application intent to run a tick, not proof that Catalyst still has
a Job Pool execution. RUNNING means a worker has claimed the task.
"""

import logging
import os
import time
import uuid
from datetime import datetime, timezone

from connections.repository import scan_crm_provider
from pipeline.shared import (
    catalyst_datetime_now,
    catalyst_error_details,
    canonical_hash,
    job_identifier,
)


LOGGER = logging.getLogger(__name__)

SALESFORCE_TASK_TYPE = "ORCHESTRATE_SALESFORCE_SCAN"
SALESFORCE_ORCHESTRATE_VERSION = "salesforce-orchestrate-v1"
SALESFORCE_CRM_PROVIDER = "salesforce"
# Match the Zoho worker lease window so Catalyst has time to start the job
# before a second submit is considered.
QUEUED_STARTUP_GRACE_SECONDS = 10 * 60


def salesforce_orchestrate_task_key(scan_id):
    return canonical_hash(
        {
            "task_type": SALESFORCE_TASK_TYPE,
            "scan_id": scan_id,
            "version": SALESFORCE_ORCHESTRATE_VERSION,
        }
    )


def _worker_target():
    pool_name = os.environ.get("SALESFORCE_WORKER_JOB_POOL_NAME", "")
    function_name = os.environ.get("SALESFORCE_WORKER_FUNCTION_NAME", "")
    return pool_name, function_name


def _orchestration_log(event, **fields):
    parts = [event]
    for key in (
        "taskId",
        "scanId",
        "pipeline_task_status",
        "provider_job_id",
        "catalyst_job_id",
    ):
        value = fields.get(key)
        if value not in (None, ""):
            parts.append(f"{key}={value}")
    for key, value in fields.items():
        if key in {
            "taskId",
            "scanId",
            "pipeline_task_status",
            "provider_job_id",
            "catalyst_job_id",
        }:
            continue
        if value not in (None, ""):
            parts.append(f"{key}={value}")
    LOGGER.info(" ".join(str(part) for part in parts))


def _parse_catalyst_datetime(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text = str(value or "").strip()
    if not text:
        raise ValueError("empty datetime")
    for date_format in (
        "%Y-%m-%d %H:%M:%S:%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
    ):
        try:
            return datetime.strptime(text, date_format).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def queued_is_stale(task_row, now=None):
    """QUEUED older than the startup grace, with no RUNNING claim."""
    if str((task_row or {}).get("status") or "") != "QUEUED":
        return False
    raw = (task_row or {}).get("enqueued_at")
    if not raw:
        return True
    try:
        enqueued_at = _parse_catalyst_datetime(raw)
    except (TypeError, ValueError):
        return True
    now = now or datetime.now(timezone.utc)
    age = (now - enqueued_at).total_seconds()
    return age > QUEUED_STARTUP_GRACE_SECONDS


def running_is_stale(task_row, now=None):
    """RUNNING with an expired or missing lease is not a live Catalyst job."""
    if str((task_row or {}).get("status") or "") != "RUNNING":
        return False
    raw = (task_row or {}).get("lease_expires_at")
    if not raw:
        return True
    try:
        expires = _parse_catalyst_datetime(raw)
    except (TypeError, ValueError):
        return True
    now = now or datetime.now(timezone.utc)
    return expires <= now


def find_salesforce_orchestrate_task(zcql, scan_id):
    task_key = salesforce_orchestrate_task_key(scan_id)
    results = zcql.execute_query(
        f"select * from pipeline_tasks where task_key = '{task_key}' limit 1"
    )
    if not results:
        return None
    return results[0]["pipeline_tasks"]


def ensure_salesforce_orchestrate_task(datastore, zcql, scan_row):
    """Return the durable Salesforce orchestrate row, creating it if needed."""
    scan_id = scan_row.get("scan_id")
    task_row = find_salesforce_orchestrate_task(zcql, scan_id)
    if task_row:
        return task_row
    return datastore.table("pipeline_tasks").insert_row(
        {
            "task_id": f"task_{uuid.uuid4().hex}",
            "task_key": salesforce_orchestrate_task_key(scan_id),
            "scan_row_id": scan_row["ROWID"],
            "task_type": SALESFORCE_TASK_TYPE,
            "status": "PLANNED",
            "attempt_count": 0,
        }
    )


def submit_salesforce_orchestrate_job(app, task_id):
    """Submit one Salesforce Job Function job. Platform retries are not enabled."""
    pool_name, function_name = _worker_target()
    if not pool_name or not function_name:
        raise RuntimeError("SALESFORCE_WORKER_NOT_CONFIGURED")

    job_name = f"sf_{canonical_hash(f'{task_id}:{time.time_ns()}')[:16]}"
    job_payload = {
        "job_name": job_name,
        "jobpool_name": pool_name,
        "target_type": "Function",
        "target_name": function_name,
        "params": {"taskId": task_id},
    }
    return app.job_scheduling().job.submit_job(job_payload), pool_name, function_name


def _task_snapshot(task_row):
    """Safe enqueue diagnostics. pipeline_tasks has started_at, not claimed_at."""
    return {
        "taskId": (task_row or {}).get("task_id"),
        "pipeline_task_status": (task_row or {}).get("status"),
        "started_at": (task_row or {}).get("started_at"),
        "lease_expires_at": (task_row or {}).get("lease_expires_at"),
        "enqueued_at": (task_row or {}).get("enqueued_at"),
        "attempt_count": (task_row or {}).get("attempt_count"),
        "controlled_error_code": (task_row or {}).get("controlled_error_code"),
        "catalyst_job_id": (task_row or {}).get("catalyst_job_id"),
        "runningIsStale": running_is_stale(task_row),
        "queuedIsStale": queued_is_stale(task_row),
    }


def _already_active(task_row, scan_row, reason):
    snapshot = _task_snapshot(task_row)
    _orchestration_log(
        "SALESFORCE_WORKER_ALREADY_ACTIVE",
        taskId=snapshot["taskId"],
        scanId=scan_row.get("scan_id"),
        pipeline_task_status=snapshot["pipeline_task_status"],
        catalyst_job_id=snapshot["catalyst_job_id"],
        reason=reason,
        submitted="false",
        submit_job_called="false",
        started_at=snapshot["started_at"],
        lease_expires_at=snapshot["lease_expires_at"],
        enqueued_at=snapshot["enqueued_at"],
        runningIsStale=snapshot["runningIsStale"],
        queuedIsStale=snapshot["queuedIsStale"],
        attempt_count=snapshot["attempt_count"],
        controlled_error_code=snapshot["controlled_error_code"],
    )
    return {
        "ok": True,
        "alreadyActive": True,
        "submitted": False,
        "submitJobCalled": False,
        "task": task_row,
        "reason": reason,
        "diagnostics": snapshot,
    }


def _submit_queued_tick(app, datastore, scan_row, task_row, *, stale_recovery=False):
    pool_name, function_name = _worker_target()
    if not pool_name or not function_name:
        LOGGER.error(
            "Salesforce worker not configured scanId=%s taskId=%s crm_provider=salesforce",
            scan_row.get("scan_id"),
            task_row.get("task_id"),
        )
        return {
            "ok": False,
            "code": "SALESFORCE_WORKER_NOT_CONFIGURED",
            "task": task_row,
            "submitJobCalled": False,
            "diagnostics": _task_snapshot(task_row),
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
    if stale_recovery:
        prior_status = str(task_row.get("status") or "")
        _orchestration_log(
            "SALESFORCE_STALE_RUNNING_RECOVERY"
            if prior_status == "RUNNING"
            else "SALESFORCE_STALE_QUEUED_RECOVERY",
            taskId=task_row.get("task_id"),
            scanId=scan_row.get("scan_id"),
            pipeline_task_status="QUEUED",
            catalyst_job_id=task_row.get("catalyst_job_id"),
            graceSeconds=QUEUED_STARTUP_GRACE_SECONDS,
            priorStatus=prior_status,
        )
    _orchestration_log(
        "SALESFORCE_SUBMIT_JOB_ATTEMPT",
        taskId=task_row.get("task_id"),
        scanId=scan_row.get("scan_id"),
        pipeline_task_status="QUEUED",
        staleRecovery=stale_recovery,
        submit_job_called="true",
        pool=pool_name,
        function=function_name,
    )
    try:
        job_response, pool_name, function_name = submit_salesforce_orchestrate_job(
            app, task_row["task_id"]
        )
        catalyst_job_id = job_identifier(job_response)
    except Exception as exc:  # noqa: BLE001 - submission outcome may be ambiguous
        catalyst_error = catalyst_error_details(exc)
        LOGGER.exception(
            "Salesforce worker enqueue failed scanId=%s taskId=%s crm_provider=salesforce",
            scan_row.get("scan_id"),
            task_row.get("task_id"),
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
                "Could not persist Salesforce worker job id scanId=%s taskId=%s",
                scan_row.get("scan_id"),
                task_row.get("task_id"),
            )
    _orchestration_log(
        "SALESFORCE_WORKER_SUBMITTED",
        taskId=task_row.get("task_id"),
        scanId=scan_row.get("scan_id"),
        pipeline_task_status="QUEUED",
        catalyst_job_id=catalyst_job_id,
        pool=pool_name,
        function=function_name,
        staleRecovery=stale_recovery,
        submit_job_called="true",
        crm_provider="salesforce",
    )
    return {
        "ok": True,
        "alreadyActive": False,
        "submitted": True,
        "submitJobCalled": True,
        "staleRecovery": stale_recovery,
        "task": {**task_row, "status": "QUEUED", "catalyst_job_id": catalyst_job_id},
        "workerJobId": catalyst_job_id,
        "jobPoolName": pool_name,
        "functionName": function_name,
        "diagnostics": {
            **_task_snapshot(task_row),
            "pipeline_task_status": "QUEUED",
        },
    }


def enqueue_salesforce_orchestrate_scan(app, datastore, scan_row):
    """Queue ORCHESTRATE_SALESFORCE_SCAN unless a live tick owns the task."""
    if scan_crm_provider(scan_row) != SALESFORCE_CRM_PROVIDER:
        return {
            "ok": False,
            "code": "WRONG_CRM_PROVIDER",
        }

    zcql = app.zcql()
    try:
        task_row = ensure_salesforce_orchestrate_task(datastore, zcql, scan_row)
    except Exception:
        LOGGER.exception(
            "Could not persist Salesforce pipeline task scanId=%s crm_provider=salesforce",
            scan_row.get("scan_id"),
        )
        return {
            "ok": False,
            "code": "SALESFORCE_WORKER_TASK_CREATE_FAILED",
        }

    snapshot = _task_snapshot(task_row)
    status = str(task_row.get("status") or "")
    _orchestration_log(
        "SALESFORCE_ADVANCE_ENQUEUE_DECISION",
        taskId=snapshot["taskId"],
        scanId=scan_row.get("scan_id"),
        pipeline_task_status=status,
        started_at=snapshot["started_at"],
        lease_expires_at=snapshot["lease_expires_at"],
        enqueued_at=snapshot["enqueued_at"],
        attempt_count=snapshot["attempt_count"],
        controlled_error_code=snapshot["controlled_error_code"],
        catalyst_job_id=snapshot["catalyst_job_id"],
        runningIsStale=snapshot["runningIsStale"],
        queuedIsStale=snapshot["queuedIsStale"],
        staleRunningRecoverySetsPlanned="false",
    )
    if status == "RUNNING":
        if running_is_stale(task_row):
            return _submit_queued_tick(
                app, datastore, scan_row, task_row, stale_recovery=True
            )
        return _already_active(task_row, scan_row, "running")
    if status == "QUEUED":
        if queued_is_stale(task_row):
            return _submit_queued_tick(
                app, datastore, scan_row, task_row, stale_recovery=True
            )
        return _already_active(task_row, scan_row, "queued_startup_grace")
    if status == "OUTCOME_UNKNOWN":
        _orchestration_log(
            "SALESFORCE_WORKER_ENQUEUE_BLOCKED",
            taskId=snapshot["taskId"],
            scanId=scan_row.get("scan_id"),
            pipeline_task_status=status,
            submit_job_called="false",
            reason="WORKER_ENQUEUE_OUTCOME_UNKNOWN",
            started_at=snapshot["started_at"],
            lease_expires_at=snapshot["lease_expires_at"],
            enqueued_at=snapshot["enqueued_at"],
        )
        return {
            "ok": False,
            "code": "WORKER_ENQUEUE_OUTCOME_UNKNOWN",
            "task": task_row,
            "submitJobCalled": False,
            "diagnostics": snapshot,
        }
    if status == "SUCCEEDED" and str(scan_row.get("status") or "") == "COMPLETED":
        return {
            "ok": True,
            "alreadyComplete": True,
            "submitted": False,
            "task": task_row,
        }
    if status not in {"PLANNED", "PAUSED_RETRYABLE", "SUCCEEDED"}:
        _orchestration_log(
            "SALESFORCE_WORKER_ENQUEUE_BLOCKED",
            taskId=snapshot["taskId"],
            scanId=scan_row.get("scan_id"),
            pipeline_task_status=status,
            submit_job_called="false",
            reason="PIPELINE_TASK_STATE_CONFLICT",
        )
        return {
            "ok": False,
            "code": "PIPELINE_TASK_STATE_CONFLICT",
            "task": task_row,
            "submitJobCalled": False,
            "diagnostics": snapshot,
        }

    return _submit_queued_tick(app, datastore, scan_row, task_row, stale_recovery=False)
