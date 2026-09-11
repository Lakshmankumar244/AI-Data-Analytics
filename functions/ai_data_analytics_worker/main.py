"""Catalyst Job Function entry point for durable analytics tasks."""

import json
import logging
from datetime import datetime, timedelta, timezone

import zcatalyst_sdk

from worker.dispatcher import dispatch_task
from worker.enqueue import mark_orchestrate_queued, submit_orchestrate_job
from worker.profiler import logger as profile_logger
from worker.task_state import catalyst_datetime, query_one


logger = logging.getLogger(__name__)


def handler(job_request, context):
    app = zcatalyst_sdk.initialize()
    datastore = app.datastore()
    task_table = datastore.table("pipeline_tasks")
    task_row = None
    try:
        params = job_request.get_all_job_params() or {}
        task_id = params.get("taskId")
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("taskId is required")

        safe_task_id = task_id.replace("'", "''")
        task_row = query_one(
            app.zcql(),
            f"select * from pipeline_tasks where task_id = '{safe_task_id}' limit 1",
            "pipeline_tasks",
        )
        if not task_row:
            raise ValueError("Pipeline task was not found")
        if task_row.get("status") == "SUCCEEDED":
            logger.info("Pipeline task %s was already completed", task_id)
            context.close_with_success()
            return
        if task_row.get("status") not in {
            "PLANNED",
            "QUEUED",
            "PAUSED_RETRYABLE",
            "OUTCOME_UNKNOWN",
        }:
            raise ValueError(
                f"Pipeline task cannot run from state {task_row.get('status')}"
            )

        now_utc = datetime.now(timezone.utc)
        attempt_count = int(task_row.get("attempt_count") or 0) + 1
        profile_logger.info(
            "SCAN_PROFILE %s",
            json.dumps(
                {
                    "scope": "worker_start",
                    "stage": "lease_and_dispatch",
                    "start": now_utc.isoformat(),
                    "taskId": task_id,
                    "taskType": task_row.get("task_type"),
                    "attemptCount": attempt_count,
                    "priorStatus": task_row.get("status"),
                    "retry": attempt_count > 1,
                },
                default=str,
            ),
        )
        task_table.update_row(
            {
                "ROWID": task_row["ROWID"],
                "status": "RUNNING",
                "attempt_count": attempt_count,
                "started_at": catalyst_datetime(now_utc),
                "lease_expires_at": catalyst_datetime(
                    now_utc + timedelta(minutes=10)
                ),
                "controlled_error_code": "",
            }
        )

        task_type = task_row.get("task_type")
        result = dispatch_task(app, task_row)

        if task_type == "ORCHESTRATE_SCAN" and isinstance(result, dict):
            outcome = result.get("outcome")
            if outcome == "YIELDED":
                retry_after = int(result.get("retryAfterSeconds") or 60)
                reason = result.get("reason")
                # Bulk Read polling uses next_retry_at to gate Zoho GETs. Do not
                # schedule a OneTime Cron for that wait; Cron adds 15–25s+ latency.
                delay_seconds = (
                    0
                    if reason in {"provider_processing", "next_retry_at"}
                    else retry_after
                )
                mark_orchestrate_queued(datastore, task_row)
                _job_response, delayed, catalyst_job_id = submit_orchestrate_job(
                    app, task_id, delay_seconds=delay_seconds
                )
                if catalyst_job_id:
                    try:
                        task_table.update_row(
                            {
                                "ROWID": task_row["ROWID"],
                                "catalyst_job_id": catalyst_job_id,
                            }
                        )
                    except Exception:
                        logger.exception(
                            "Could not persist ORCHESTRATE_SCAN requeue job id task_id=%s",
                            task_id,
                        )
                profile_logger.info(
                    "SCAN_PROFILE %s",
                    json.dumps(
                        {
                            "scope": "ORCHESTRATE_SCAN",
                            "stage": "reenqueue",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "scanId": result.get("scanId"),
                            "bulkJobId": result.get("bulkJobId"),
                            "delaySeconds": delay_seconds,
                            "retryAfterSeconds": retry_after,
                            "nextRetryAt": result.get("nextRetryAt"),
                            "remainingSeconds": result.get("remainingSeconds"),
                            "delayed": delayed,
                            "enqueueMode": "cron" if delayed else "immediate",
                            "reason": reason,
                            "providerState": result.get("providerState"),
                            "taskId": task_id,
                            "workerJobId": catalyst_job_id,
                            "steps": result.get("steps"),
                        },
                        default=str,
                    ),
                )
                logger.info(
                    "ORCHESTRATE_SCAN yielded task_id=%s retryAfter=%s delayed=%s",
                    task_id,
                    retry_after,
                    delayed,
                )
                context.close_with_success()
                return

        task_table.update_row(
            {
                "ROWID": task_row["ROWID"],
                "status": "SUCCEEDED",
                "completed_at": catalyst_datetime(datetime.now(timezone.utc)),
                "controlled_error_code": "",
            }
        )
        logger.info(
            "Pipeline task %s completed taskType=%s result=%s",
            task_id,
            task_type,
            result,
        )
        context.close_with_success()
    except Exception as exc:  # noqa: BLE001 - persist controlled Job failure
        logger.exception("Analytics worker task failed: %s", exc)
        profile_logger.info(
            "SCAN_PROFILE %s",
            json.dumps(
                {
                    "scope": "worker_failure",
                    "stage": "task_failed",
                    "end": datetime.now(timezone.utc).isoformat(),
                    "taskId": (task_row or {}).get("task_id"),
                    "taskType": (task_row or {}).get("task_type"),
                    "attemptCount": int((task_row or {}).get("attempt_count") or 0),
                    "error": str(exc),
                },
                default=str,
            ),
        )
        if task_row:
            try:
                task_table.update_row(
                    {
                        "ROWID": task_row["ROWID"],
                        "status": "PAUSED_RETRYABLE",
                        "controlled_error_code": (
                            f"{task_row.get('task_type') or 'PIPELINE_TASK'}_FAILED"
                        )[:100],
                    }
                )
            except Exception:  # noqa: BLE001 - original failure is primary
                logger.exception("Could not persist worker task failure")
        context.close_with_failure()
