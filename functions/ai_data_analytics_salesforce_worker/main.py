"""Catalyst Job Function entry point for Salesforce extraction tasks.

Loads a pipeline_tasks row by taskId, leases it to RUNNING, then submits or
polls one Salesforce Bulk API 2.0 Query job. An existing provider_job_id is
never resubmitted. After READY_TO_DOWNLOAD the same worker downloads results
and continues through PREPARE_BATCHES / PROCESS_BATCHES.
"""

import logging
from datetime import datetime, timezone

import zcatalyst_sdk

from continue_extract import continue_salesforce_extract
from lease import (
    ALREADY_COMPLETE,
    ALREADY_RUNNING,
    claim_salesforce_task,
)
from requeue import requeue_salesforce_orchestrate_task
from submit_bulk import submit_one_salesforce_bulk_job
from task_resolve import (
    EXPORT_FIX_XLSX,
    SALESFORCE_TASK_TYPE,
    SalesforceWorkerError,
    resolve_salesforce_task,
)


logger = logging.getLogger(__name__)

ALLOWED_TASK_TYPES = frozenset({SALESFORCE_TASK_TYPE, EXPORT_FIX_XLSX})


def _job_params(job_request):
    if job_request is None:
        return {}
    getter = getattr(job_request, "get_all_job_params", None)
    if not callable(getter):
        return {}
    raw = getter()
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise SalesforceWorkerError(
            "MALFORMED_PARAMS",
            "Job parameters must be an object",
        )
    return raw


def _optional_string(params, name):
    if name not in params:
        return None
    value = params[name]
    if value is None:
        return None
    if not isinstance(value, str):
        raise SalesforceWorkerError("MALFORMED_PARAMS", f"{name} must be a string")
    stripped = value.strip()
    return stripped or None


def _event_log(event, resolved=None, result=None, **fields):
    task = (resolved or {}).get("task") or {}
    bulk_id = None
    if isinstance(result, dict):
        bulk_id = result.get("providerJobId")
        fields.setdefault("catalyst_job_id", result.get("workerJobId"))
        fields.setdefault("pipeline_task_status", task.get("status"))
    parts = [event]
    payload = {
        "taskId": (resolved or {}).get("taskId") or task.get("task_id"),
        "scanId": (resolved or {}).get("scanId"),
        "pipeline_task_status": fields.pop(
            "pipeline_task_status", task.get("status")
        ),
        "provider_job_id": fields.pop("provider_job_id", bulk_id),
        "catalyst_job_id": fields.pop(
            "catalyst_job_id", task.get("catalyst_job_id")
        ),
        **fields,
    }
    for key, value in payload.items():
        if value not in (None, ""):
            parts.append(f"{key}={value}")
    logger.info(" ".join(str(part) for part in parts))


def _maybe_requeue(app, resolved, result):
    if not isinstance(result, dict) or not result.get("requeue"):
        return result
    task_row = resolved.get("task") or {}
    delay_seconds = int(result.get("retryAfterSeconds") or 0)
    try:
        requeue = requeue_salesforce_orchestrate_task(
            app, task_row, delay_seconds=delay_seconds
        )
    except Exception:
        logger.exception(
            "Salesforce worker could not requeue poll taskId=%s scanId=%s",
            resolved.get("taskId"),
            resolved.get("scanId"),
        )
        result = dict(result)
        result["requeued"] = False
        return result
    result = dict(result)
    result["requeued"] = True
    result["requeueDelayed"] = bool(requeue.get("delayed"))
    if requeue.get("workerJobId"):
        result["workerJobId"] = requeue["workerJobId"]
    _event_log(
        "SALESFORCE_TASK_REQUEUED",
        resolved,
        result,
        provider_job_id=result.get("providerJobId"),
        delaySeconds=requeue.get("delaySeconds"),
        delayed=requeue.get("delayed"),
        pipeline_task_status="QUEUED",
        catalyst_job_id=requeue.get("workerJobId"),
    )
    return result


def _mark_task_paused(app, task_row, code):
    if not task_row or not task_row.get("ROWID"):
        return
    try:
        app.datastore().table("pipeline_tasks").update_row(
            {
                "ROWID": task_row["ROWID"],
                "status": "PAUSED_RETRYABLE",
                "controlled_error_code": str(code or "SALESFORCE_WORKER_FAILED")[:100],
            }
        )
    except Exception:
        logger.exception(
            "Could not persist Salesforce worker task failure taskId=%s",
            task_row.get("task_id"),
        )


def _release_blocked_claim(app, task_row, result):
    """A finished tick with no requeue must not keep RUNNING forever.

    RETRY_BLOCKED previously left the lease in RUNNING, so HTTP /advance
    treated the task as alreadyActive and submitted no Catalyst job.
    """
    if not isinstance(result, dict) or result.get("requeue"):
        return
    if result.get("outcome") != "RETRY_BLOCKED":
        return
    if not task_row or not task_row.get("ROWID"):
        return
    try:
        app.datastore().table("pipeline_tasks").update_row(
            {
                "ROWID": task_row["ROWID"],
                "status": "PLANNED",
                "controlled_error_code": str(result.get("status") or "RETRY_BLOCKED")[:100],
            }
        )
        task_row["status"] = "PLANNED"
    except Exception:
        logger.exception(
            "Could not release Salesforce blocked claim taskId=%s",
            task_row.get("task_id"),
        )


def _mark_task_succeeded(app, task_row):
    if not task_row or not task_row.get("ROWID"):
        return
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    app.datastore().table("pipeline_tasks").update_row(
        {
            "ROWID": task_row["ROWID"],
            "status": "SUCCEEDED",
            "completed_at": now,
            "controlled_error_code": "",
        }
    )
    task_row["status"] = "SUCCEEDED"


def handler(job_request, context):
    task_row = None
    resolved = None
    app = None
    try:
        params = _job_params(job_request)
        task_id = _optional_string(params, "taskId")
        job_task_type = _optional_string(params, "taskType")
        if job_task_type and job_task_type not in ALLOWED_TASK_TYPES:
            raise SalesforceWorkerError(
                "WRONG_TASK_TYPE",
                f"Unsupported task type {job_task_type}",
            )
        if not task_id:
            raise SalesforceWorkerError("TASK_ID_REQUIRED", "taskId is required")

        app = zcatalyst_sdk.initialize()
        resolved = resolve_salesforce_task(app.zcql(), task_id)
        task_row = resolved["task"]
        claim = claim_salesforce_task(app.datastore(), task_row)
        if claim == ALREADY_COMPLETE:
            context.close_with_success()
            return {"outcome": "ALREADY_COMPLETE", "taskId": task_id}
        if claim == ALREADY_RUNNING:
            _event_log("SALESFORCE_TASK_ALREADY_RUNNING", resolved)
            context.close_with_success()
            return {
                "outcome": "ALREADY_RUNNING",
                "taskId": resolved["taskId"],
                "scanId": resolved["scanId"],
                "status": "RUNNING",
            }
        _event_log("SALESFORCE_TASK_CLAIMED", resolved, pipeline_task_status="RUNNING")
        if str(task_row.get("task_type") or "") == EXPORT_FIX_XLSX:
            from shared.fix_export import export_fix_xlsx

            result = export_fix_xlsx(app, task_row)
            _mark_task_succeeded(app, task_row)
            _event_log(
                "SALESFORCE_FIX_EXPORT_SUCCEEDED",
                resolved,
                result,
                pipeline_task_status="SUCCEEDED",
            )
            context.close_with_success()
            return result
        result = submit_one_salesforce_bulk_job(app, resolved)
        if isinstance(result, dict) and result.get("outcome") in {
            "READY_TO_DOWNLOAD",
            "WAITING_FOR_DOWNLOAD",
            "PROCESS_NEEDED",
        }:
            continued = continue_salesforce_extract(app, resolved)
            if continued:
                result = continued
        _release_blocked_claim(app, task_row, result)
        result = _maybe_requeue(app, resolved, result)
        context.close_with_success()
        return result
    except SalesforceWorkerError as exc:
        logger.error("Salesforce worker rejected job: %s", exc)
        if task_row and exc.code not in {
            "TASK_ID_REQUIRED",
            "TASK_NOT_FOUND",
            "WRONG_TASK_TYPE",
            "WRONG_CRM_PROVIDER",
            "SCAN_NOT_FOUND",
            "SCAN_NOT_OWNED",
            "MALFORMED_PARAMS",
            "PIPELINE_TASK_STATE_CONFLICT",
        }:
            _mark_task_paused(app, task_row, exc.code)
        context.close_with_failure()
        return {"outcome": "FAILED", "error": str(exc), "code": exc.code}
    except Exception as exc:  # noqa: BLE001 - Job Function must close
        logger.exception("Salesforce worker failed: %s", exc)
        if task_row:
            _mark_task_paused(app, task_row, type(exc).__name__)
        context.close_with_failure()
        return {"outcome": "FAILED"}
