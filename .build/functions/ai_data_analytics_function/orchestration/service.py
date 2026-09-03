"""Choose and perform at most one resumable scan-pipeline action."""

import json
import logging

import zcatalyst_sdk

from bulk_read.download import download_bulk_read_result
from bulk_read.prepare import prepare_bulk_read
from bulk_read.status import refresh_bulk_read_status
from bulk_read.submit import submit_bulk_read_job
from common.core import (
    AuthenticationRequired,
    foreign_row_id,
    get_current_user_id,
    json_response,
)
from orchestration.repository import load_scan_state
from pipeline.task_routes import enqueue_prepare_batches, enqueue_process_batches
from scans.routes import discover_scan


LOGGER = logging.getLogger(__name__)
ACTIVE_TASK_STATES = {"QUEUED", "RUNNING"}


def _latest_task(state, bulk_row, task_type):
    matches = [
        task
        for task in state["tasks"]
        if str(foreign_row_id(task.get("bulk_job_row_id"))) == str(bulk_row["ROWID"])
        and task.get("task_type") == task_type
    ]
    return max(matches, key=lambda row: int(row.get("ROWID") or 0), default=None)


def choose_action(state):
    """Return the next deterministic action without changing any state."""
    scan_status = str(state["scan"].get("status") or "")
    if scan_status == "COMPLETED":
        return {"name": "COMPLETE", "next": None}
    if scan_status == "FAILED_TERMINAL":
        return {"name": "BLOCKED", "next": "REVIEW_FAILURE"}
    if scan_status in {"CREATED", "DISCOVERING", "PAUSED_RETRYABLE"}:
        return {"name": "DISCOVER", "next": "PREPARE_BULK"}

    modules = sorted(
        state["modules"], key=lambda row: str(row.get("module_api_name") or "")
    )
    if not modules:
        return {"name": "BLOCKED", "next": "REVIEW_SCAN_PLAN"}

    all_jobs = [
        job
        for module in modules
        for job in state["bulk_jobs_by_module"].get(str(module["ROWID"]), [])
    ]
    if not all_jobs:
        return {"name": "PREPARE_BULK", "next": "SUBMIT_BULK"}

    for module in modules:
        jobs = sorted(
            state["bulk_jobs_by_module"].get(str(module["ROWID"]), []),
            key=lambda row: (
                int(row.get("provider_page") or 0),
                str(row.get("bulk_job_id") or ""),
            ),
        )
        if not jobs:
            return {"name": "BLOCKED", "next": "REVIEW_BULK_PLAN"}
        for bulk in jobs:
            status = str(bulk.get("status") or "")
            target = {"bulk": bulk, "module": module}
            if status == "PLANNED":
                return {
                    "name": "SUBMIT_BULK",
                    "next": "CHECK_BULK_STATUS",
                    **target,
                }
            if status == "SUBMITTED" or (
                status == "PROCESSING" and not bulk.get("source_file_id")
            ):
                return {
                    "name": "CHECK_BULK_STATUS",
                    "next": "CHECK_BULK_STATUS",
                    **target,
                }
            if status in {"READY_TO_DOWNLOAD", "DOWNLOAD_RETRYABLE"}:
                return {
                    "name": "DOWNLOAD_RESULT",
                    "next": "PREPARE_BATCHES",
                    **target,
                }
            if status == "DOWNLOADED":
                task = _latest_task(state, bulk, "PREPARE_BATCHES")
                if task and task.get("status") in ACTIVE_TASK_STATES:
                    return {
                        "name": "WAIT_FOR_WORKER",
                        "next": "PREPARE_BATCHES",
                        "task": task,
                        **target,
                    }
                if task and task.get("status") == "OUTCOME_UNKNOWN":
                    return {
                        "name": "BLOCKED",
                        "next": "REVIEW_WORKER_JOB",
                        "task": task,
                        **target,
                    }
                return {
                    "name": "PREPARE_BATCHES",
                    "next": "PROCESS_BATCHES",
                    **target,
                }
            if status in {"PROCESSING_PLANNED", "PROCESSING"} and bulk.get(
                "source_file_id"
            ):
                task = _latest_task(state, bulk, "PROCESS_BATCHES")
                if task and task.get("status") in ACTIVE_TASK_STATES:
                    return {
                        "name": "WAIT_FOR_WORKER",
                        "next": "PROCESS_BATCHES",
                        "task": task,
                        **target,
                    }
                if task and task.get("status") == "OUTCOME_UNKNOWN":
                    return {
                        "name": "BLOCKED",
                        "next": "REVIEW_WORKER_JOB",
                        "task": task,
                        **target,
                    }
                return {
                    "name": "PROCESS_BATCHES",
                    "next": "WAIT_FOR_WORKER",
                    **target,
                }
            if status == "PROCESSED":
                continue
            return {"name": "BLOCKED", "next": "REVIEW_BULK_JOB", **target}

    return {"name": "WAIT_FOR_COMPLETION", "next": "REFRESH_STATUS"}


def _response_body(response):
    try:
        body = response.get_json(silent=True)
    except Exception:  # noqa: BLE001 - preserve the delegated HTTP response
        body = None
    if isinstance(body, dict):
        return body
    try:
        parsed = json.loads(response.get_data(as_text=True))
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _execute(action, request, datastore, scan_id):
    name = action["name"]
    if name == "DISCOVER":
        return discover_scan(request, datastore, scan_id)
    if name == "PREPARE_BULK":
        return prepare_bulk_read(request, datastore, scan_id)

    bulk_job_id = action["bulk"]["bulk_job_id"]
    handlers = {
        "SUBMIT_BULK": submit_bulk_read_job,
        "CHECK_BULK_STATUS": refresh_bulk_read_status,
        "DOWNLOAD_RESULT": download_bulk_read_result,
        "PREPARE_BATCHES": enqueue_prepare_batches,
        "PROCESS_BATCHES": enqueue_process_batches,
    }
    return handlers[name](request, datastore, scan_id, bulk_job_id)


def advance_scan(request, datastore, scan_id):
    """Perform no more than one action, then report the newly durable state."""
    try:
        zcql = zcatalyst_sdk.initialize().zcql()
        user_id = get_current_user_id(request)
        state = load_scan_state(zcql, scan_id, user_id)
        if not state:
            return json_response(
                {"error": {"code": "SCAN_NOT_FOUND", "message": "Scan was not found"}},
                404,
            )

        action = choose_action(state)
        passive = {"COMPLETE", "WAIT_FOR_WORKER", "WAIT_FOR_COMPLETION", "BLOCKED"}
        if action["name"] in passive:
            task = action.get("task") or {}
            bulk = action.get("bulk") or {}
            blocked = action["name"] == "BLOCKED"
            return json_response(
                {
                    "scanId": scan_id,
                    "currentStatus": state["scan"].get("status"),
                    "operationPerformed": "NONE",
                    "nextAction": action.get("next"),
                    "waitingForProvider": action["name"]
                    in {"WAIT_FOR_WORKER", "WAIT_FOR_COMPLETION"},
                    "blocked": blocked,
                    "bulkJobId": bulk.get("bulk_job_id"),
                    "bulkJobStatus": bulk.get("status"),
                    "taskId": task.get("task_id"),
                    "taskStatus": task.get("status"),
                    "zohoApiCalls": 0,
                    "zohoCreditsConsumed": 0,
                },
                409
                if blocked
                else (202 if action["name"] == "WAIT_FOR_WORKER" else 200),
            )

        delegated = _execute(action, request, datastore, scan_id)
        body = _response_body(delegated)
        if delegated.status_code == 429 and body.get("pollingDeferred"):
            return json_response(
                {
                    "scanId": scan_id,
                    "currentStatus": state["scan"].get("status"),
                    "operationPerformed": "NONE",
                    "nextAction": "CHECK_BULK_STATUS",
                    "waitingForProvider": True,
                    "pollingDeferred": True,
                    "retryAfterSeconds": int(body.get("retryAfterSeconds") or 60),
                    "bulkJobId": body.get("bulkJobId"),
                    "zohoApiCalls": 0,
                    "zohoCreditsConsumed": 0,
                },
                202,
            )
        if delegated.status_code >= 400:
            return delegated

        refreshed = load_scan_state(zcql, scan_id, user_id)
        following = choose_action(refreshed) if refreshed else {"name": None}
        return json_response(
            {
                "scanId": scan_id,
                "currentStatus": refreshed["scan"].get("status")
                if refreshed
                else body.get("status"),
                "operationPerformed": action["name"],
                "nextAction": following.get("name") or following.get("next"),
                "waitingForProvider": following.get("name")
                in {"CHECK_BULK_STATUS", "WAIT_FOR_WORKER", "WAIT_FOR_COMPLETION"},
                "bulkJobId": body.get("bulkJobId"),
                "taskId": body.get("taskId"),
                "taskStatus": body.get("taskStatus"),
                "retryAfterSeconds": body.get("retryAfterSeconds"),
                "userDirectory": body.get("userDirectory")
                if action["name"] == "DISCOVER"
                else None,
                "zohoApiCalls": int(
                    body.get("zohoApiCalls", body.get("crmApiCalls", 0)) or 0
                ),
                "zohoCreditsConsumed": int(
                    body.get("zohoCreditsConsumed", body.get("creditsConsumed", 0))
                    or 0
                ),
            },
            delegated.status_code,
        )
    except AuthenticationRequired:
        raise
    except Exception as exc:  # noqa: BLE001 - expose only a controlled error
        LOGGER.exception("Could not advance scan scan_id=%s: %s", scan_id, exc)
        return json_response(
            {
                "error": {
                    "code": "SCAN_ADVANCE_FAILED",
                    "message": "The scan could not be advanced",
                }
            },
            500,
        )
