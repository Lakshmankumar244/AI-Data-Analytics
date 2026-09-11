"""Worker-owned scan state machine using the existing Job Function."""

import json
import logging
from datetime import datetime, timezone

from bulk_read.download import download_bulk_read_result
from bulk_read.prepare import prepare_bulk_read
from bulk_read.status import refresh_bulk_read_status
from bulk_read.submit import submit_bulk_read_job
from orchestration.choose import choose_action
from scans.discover import discover_scan
from tasks.prepare_batches import prepare_batches
from worker.continue_process import continue_to_process_batches
from worker.profiler import logger as profile_logger
from worker.scan_state import load_scan_state

LOGGER = logging.getLogger(__name__)

MAX_STEPS_PER_TICK = 40
WORKER_WAIT_RETRY_SECONDS = 5


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _response_body(response):
    try:
        body = response.get_json(silent=True)
    except Exception:  # noqa: BLE001 - worker copies may not be Flask responses
        body = None
    if isinstance(body, dict):
        return body
    if isinstance(response, dict):
        return response
    try:
        parsed = json.loads(response.get_data(as_text=True))
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError, AttributeError):
        return {}


def _status_code(response):
    if hasattr(response, "status_code"):
        return int(response.status_code)
    if isinstance(response, dict):
        return int(response.get("status_code") or 200)
    return 200


def _log(stage, **payload):
    profile_logger.info(
        "SCAN_PROFILE %s",
        json.dumps(
            {
                "scope": "ORCHESTRATE_SCAN",
                "stage": stage,
                "timestamp": _utc_now(),
                **payload,
            },
            default=str,
        ),
    )


def _synthetic_batch_task(orchestrate_task, action):
    bulk = action.get("bulk") or {}
    module = action.get("module") or {}
    return {
        "task_id": orchestrate_task.get("task_id"),
        "attempt_count": orchestrate_task.get("attempt_count") or 0,
        "status": "RUNNING",
        "scan_row_id": orchestrate_task.get("scan_row_id"),
        "scan_module_row_id": module.get("ROWID"),
        "bulk_job_row_id": bulk.get("ROWID"),
    }


def _execute_action(app, datastore, scan_id, action, orchestrate_task):
    name = action["name"]
    if name == "DISCOVER":
        return discover_scan(None, datastore, scan_id)
    if name == "PREPARE_BULK":
        return prepare_bulk_read(None, datastore, scan_id)
    if name == "PREPARE_BATCHES":
        synthetic = _synthetic_batch_task(orchestrate_task, action)
        prepare_result = prepare_batches(app, synthetic)
        process_result = continue_to_process_batches(app, synthetic)
        return {
            "status_code": 200,
            "prepare": prepare_result,
            "processBatches": process_result,
        }
    if name == "PROCESS_BATCHES":
        synthetic = _synthetic_batch_task(orchestrate_task, action)
        process_result = continue_to_process_batches(app, synthetic)
        return {"status_code": 200, "processBatches": process_result}

    bulk_job_id = action["bulk"]["bulk_job_id"]
    handlers = {
        "SUBMIT_BULK": submit_bulk_read_job,
        "CHECK_BULK_STATUS": refresh_bulk_read_status,
        "DOWNLOAD_RESULT": download_bulk_read_result,
    }
    return handlers[name](None, datastore, scan_id, bulk_job_id)


def orchestrate_scan(app, task_row):
    zcql = app.zcql()
    datastore = app.datastore()
    scan_row_id = task_row.get("scan_row_id")
    if scan_row_id is None:
        raise ValueError("ORCHESTRATE_SCAN is missing scan_row_id")
    scan_rows = zcql.execute_query(
        f"select * from scan_jobs where ROWID = {int(scan_row_id)} limit 1"
    )
    if not scan_rows:
        raise ValueError("Scan was not found")
    scan_id = scan_rows[0]["scan_jobs"]["scan_id"]
    current_status = scan_rows[0]["scan_jobs"].get("status")

    steps = []
    for _ in range(MAX_STEPS_PER_TICK):
        state = load_scan_state(zcql, scan_id)
        if not state:
            raise ValueError("Scan was not found")
        action = choose_action(state)
        name = action["name"]
        bulk_job_id = (action.get("bulk") or {}).get("bulk_job_id")
        if not steps:
            _log(
                "start",
                scanId=scan_id,
                currentStatus=state["scan"].get("status") or current_status,
                actionSelected=name,
                taskKey=task_row.get("task_key"),
                taskId=task_row.get("task_id"),
            )
        _log(
            "action_selected",
            scanId=scan_id,
            taskId=task_row.get("task_id"),
            taskKey=task_row.get("task_key"),
            actionSelected=name,
            nextAction=action.get("next"),
            currentStatus=state["scan"].get("status"),
            bulkJobId=bulk_job_id,
            bulkJobStatus=(action.get("bulk") or {}).get("status"),
        )
        steps.append(name)

        if name == "COMPLETE":
            _log(
                "completion",
                scanId=scan_id,
                finalState=state["scan"].get("status") or "COMPLETED",
                taskId=task_row.get("task_id"),
                taskKey=task_row.get("task_key"),
            )
            _log(
                "worker_owned_completion",
                scanId=scan_id,
                taskId=task_row.get("task_id"),
                steps=steps,
            )
            _log("end", scanId=scan_id, taskId=task_row.get("task_id"), outcome="COMPLETED")
            return {"outcome": "COMPLETED", "scanId": scan_id, "steps": steps}

        if name == "BLOCKED":
            _log(
                "completion",
                scanId=scan_id,
                finalState=state["scan"].get("status"),
                nextAction=action.get("next"),
                bulkJobId=bulk_job_id,
                taskId=task_row.get("task_id"),
                taskKey=task_row.get("task_key"),
            )
            raise ValueError(
                f"ORCHESTRATE_SCAN blocked next={action.get('next')}"
            )

        if name in {"WAIT_FOR_WORKER", "WAIT_FOR_COMPLETION"}:
            retry_after = WORKER_WAIT_RETRY_SECONDS
            _log(
                "yielded_next_retry_at",
                scanId=scan_id,
                taskId=task_row.get("task_id"),
                reason=name,
                retryAfterSeconds=retry_after,
            )
            _log("end", scanId=scan_id, taskId=task_row.get("task_id"), outcome="YIELDED")
            return {
                "outcome": "YIELDED",
                "reason": name,
                "retryAfterSeconds": retry_after,
                "scanId": scan_id,
                "bulkJobId": bulk_job_id,
                "nextRetryAt": (action.get("bulk") or {}).get("next_retry_at"),
                "steps": steps,
            }

        if name == "CHECK_BULK_STATUS":
            _log(
                "CHECK_BULK_STATUS",
                scanId=scan_id,
                bulkJobId=bulk_job_id,
                bulkJobStatus=(action.get("bulk") or {}).get("status"),
                taskId=task_row.get("task_id"),
                taskKey=task_row.get("task_key"),
            )

        response = _execute_action(app, datastore, scan_id, action, task_row)
        body = _response_body(response)
        status_code = _status_code(response)

        if name == "CHECK_BULK_STATUS":
            retry_after = int(body.get("retryAfterSeconds") or 0)
            still_processing = body.get("pollingDeferred") or str(
                body.get("status") or ""
            ) in {"SUBMITTED", "PROCESSING"}
            if status_code == 429 and body.get("pollingDeferred"):
                _log(
                    "yielded_next_retry_at",
                    scanId=scan_id,
                    taskId=task_row.get("task_id"),
                    reason="next_retry_at",
                    retryAfterSeconds=retry_after or 60,
                    bulkJobId=body.get("bulkJobId"),
                )
                _log("end", scanId=scan_id, taskId=task_row.get("task_id"), outcome="YIELDED")
                return {
                    "outcome": "YIELDED",
                    "reason": "next_retry_at",
                    "retryAfterSeconds": retry_after or 60,
                    "scanId": scan_id,
                    "bulkJobId": body.get("bulkJobId") or bulk_job_id,
                    "nextRetryAt": (action.get("bulk") or {}).get("next_retry_at"),
                    "remainingSeconds": retry_after or 60,
                    "steps": steps,
                }
            if status_code < 400 and still_processing and not body.get(
                "downloadAvailable"
            ):
                _log(
                    "yielded_next_retry_at",
                    scanId=scan_id,
                    taskId=task_row.get("task_id"),
                    reason="provider_processing",
                    retryAfterSeconds=retry_after or 60,
                    bulkJobId=body.get("bulkJobId"),
                    providerState=body.get("providerState"),
                )
                _log("end", scanId=scan_id, taskId=task_row.get("task_id"), outcome="YIELDED")
                return {
                    "outcome": "YIELDED",
                    "reason": "provider_processing",
                    "retryAfterSeconds": retry_after or 60,
                    "scanId": scan_id,
                    "bulkJobId": body.get("bulkJobId") or bulk_job_id,
                    "nextRetryAt": (action.get("bulk") or {}).get("next_retry_at"),
                    "providerState": body.get("providerState"),
                    "steps": steps,
                }

        if status_code >= 400:
            error = (body.get("error") or {}).get("code") or f"HTTP_{status_code}"
            if name == "CHECK_BULK_STATUS" and str(body.get("status") or "") == "FAILED_TERMINAL":
                _log(
                    "completion",
                    scanId=scan_id,
                    finalState="FAILED_TERMINAL",
                    bulkJobId=body.get("bulkJobId") or bulk_job_id,
                    taskId=task_row.get("task_id"),
                    taskKey=task_row.get("task_key"),
                )
            raise ValueError(f"ORCHESTRATE_SCAN action {name} failed: {error}")

    raise ValueError("ORCHESTRATE_SCAN exceeded the safe step limit for one tick")
