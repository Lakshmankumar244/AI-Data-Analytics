"""Choose and perform at most one resumable scan-pipeline action."""

import json
import logging
from datetime import datetime, timezone

import zcatalyst_sdk

from bulk_read.download import download_bulk_read_result
from bulk_read.prepare import prepare_bulk_read
from bulk_read.status import refresh_bulk_read_status
from bulk_read.submit import submit_bulk_read_job
from common.core import (
    AuthenticationRequired,
    from_catalyst_datetime,
    get_current_user_id,
    json_response,
)
from common.profiler import profile_stage
from orchestration.choose import choose_action, orchestrate_owns_scan
from orchestration.repository import load_scan_state
from pipeline.orchestrate_enqueue import enqueue_orchestrate_scan
from pipeline.task_routes import enqueue_prepare_batches, enqueue_process_batches
from scans.discover import discover_scan


LOGGER = logging.getLogger(__name__)


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


def _retry_after_seconds(action):
    bulk = action.get("bulk") or {}
    next_retry_value = bulk.get("next_retry_at")
    if not next_retry_value:
        return None
    try:
        retry_at = from_catalyst_datetime(next_retry_value)
        remaining = int((retry_at - datetime.now(timezone.utc)).total_seconds())
        return max(1, remaining) if remaining > 0 else None
    except (TypeError, ValueError):
        return None


def _status_payload(scan_id, state, action, *, worker_owned, blocked=False, extra=None):
    task = action.get("task") or {}
    bulk = action.get("bulk") or {}
    payload = {
        "scanId": scan_id,
        "currentStatus": state["scan"].get("status"),
        "operationPerformed": "NONE",
        "nextAction": action.get("name") or action.get("next"),
        "waitingForProvider": action.get("name")
        in {
            "CHECK_BULK_STATUS",
            "WAIT_FOR_WORKER",
            "WAIT_FOR_COMPLETION",
        },
        "blocked": blocked,
        "workerOwned": worker_owned,
        "orchestrationOwner": "WORKER" if worker_owned else "HTTP",
        "bulkJobId": bulk.get("bulk_job_id"),
        "bulkJobStatus": bulk.get("status"),
        "taskId": task.get("task_id"),
        "taskStatus": task.get("status"),
        "retryAfterSeconds": _retry_after_seconds(action),
        "zohoApiCalls": 0,
        "zohoCreditsConsumed": 0,
    }
    if extra:
        payload.update(extra)
    return payload


def _log_advance_blocked(scan_id, state, action, task, reason):
    LOGGER.info(
        "SCAN_PROFILE %s",
        json.dumps(
            {
                "scope": "ORCHESTRATE_SCAN",
                "stage": "advance_blocked",
                "scanId": scan_id,
                "reason": reason,
                "actionSelected": action.get("name"),
                "nextAction": action.get("next"),
                "currentStatus": state["scan"].get("status"),
                "orchestrateTaskId": (task or {}).get("task_id"),
                "orchestrateTaskStatus": (task or {}).get("status"),
                "bulkJobId": (action.get("bulk") or {}).get("bulk_job_id"),
            },
            default=str,
        ),
    )


def advance_scan(request, datastore, scan_id):
    """Report status while ORCHESTRATE_SCAN owns the scan; otherwise recover."""
    try:
        app = zcatalyst_sdk.initialize()
        zcql = app.zcql()
        user_id = get_current_user_id(request)
        with profile_stage("orchestration", "load_scan_state", scanId=scan_id):
            state = load_scan_state(zcql, scan_id, user_id)
        if not state:
            return json_response(
                {"error": {"code": "SCAN_NOT_FOUND", "message": "Scan was not found"}},
                404,
            )

        action = choose_action(state)
        owned, orchestrate_task = orchestrate_owns_scan(state)
        if owned:
            _log_advance_blocked(
                scan_id, state, action, orchestrate_task, "worker_owned"
            )
            blocked = action["name"] == "BLOCKED"
            return json_response(
                _status_payload(
                    scan_id, state, action, worker_owned=True, blocked=blocked
                )
            )

        if str(state["scan"].get("status") or "") != "COMPLETED":
            enqueue_result = enqueue_orchestrate_scan(app, datastore, state["scan"])
            if enqueue_result.get("ok"):
                LOGGER.info(
                    "SCAN_PROFILE %s",
                    json.dumps(
                        {
                            "scope": "ORCHESTRATE_SCAN",
                            "stage": "advance_enqueued",
                            "scanId": scan_id,
                            "alreadyActive": enqueue_result.get("alreadyActive"),
                            "submitted": enqueue_result.get("submitted"),
                            "taskId": (enqueue_result.get("task") or {}).get("task_id"),
                        },
                        default=str,
                    ),
                )
                refreshed = load_scan_state(zcql, scan_id, user_id) or state
                following = choose_action(refreshed)
                _log_advance_blocked(
                    scan_id,
                    refreshed,
                    following,
                    enqueue_result.get("task"),
                    "handed_to_worker",
                )
                return json_response(
                    _status_payload(
                        scan_id,
                        refreshed,
                        following,
                        worker_owned=True,
                        extra={
                            "taskId": (enqueue_result.get("task") or {}).get("task_id"),
                            "taskStatus": (enqueue_result.get("task") or {}).get(
                                "status"
                            ),
                        },
                    )
                )
            if enqueue_result.get("code") == "WORKER_ENQUEUE_OUTCOME_UNKNOWN":
                _log_advance_blocked(
                    scan_id,
                    state,
                    {"name": "BLOCKED", "next": "REVIEW_WORKER_JOB"},
                    enqueue_result.get("task"),
                    "orchestrate_outcome_unknown",
                )
                return json_response(
                    {
                        "error": {
                            "code": "WORKER_ENQUEUE_OUTCOME_UNKNOWN",
                            "message": "Inspect the Job Pool before retrying this task",
                        },
                        "taskId": (enqueue_result.get("task") or {}).get("task_id"),
                        "nextAction": "REVIEW_WORKER_JOB",
                        "workerOwned": False,
                    },
                    409,
                )

        passive = {"COMPLETE", "WAIT_FOR_WORKER", "WAIT_FOR_COMPLETION", "BLOCKED"}
        if action["name"] in passive:
            task = action.get("task") or {}
            bulk = action.get("bulk") or {}
            blocked = action["name"] == "BLOCKED"
            LOGGER.info(
                "SCAN_PROFILE %s",
                json.dumps(
                    {
                        "scope": "orchestration",
                        "stage": action["name"],
                        "scanId": scan_id,
                        "currentStatus": state["scan"].get("status"),
                        "nextAction": action.get("next"),
                        "bulkJobId": bulk.get("bulk_job_id"),
                        "bulkJobStatus": bulk.get("status"),
                        "taskId": task.get("task_id"),
                        "taskStatus": task.get("status"),
                        "taskAttemptCount": task.get("attempt_count"),
                        "waiting": True,
                        "workerOwned": False,
                    },
                    default=str,
                ),
            )
            return json_response(
                _status_payload(
                    scan_id, state, action, worker_owned=False, blocked=blocked
                ),
                409
                if blocked
                else (202 if action["name"] == "WAIT_FOR_WORKER" else 200),
            )

        with profile_stage(
            "orchestration",
            action["name"],
            scanId=scan_id,
            currentStatus=state["scan"].get("status"),
            bulkJobId=(action.get("bulk") or {}).get("bulk_job_id"),
        ):
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
                    "workerOwned": False,
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
                "workerOwned": False,
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
