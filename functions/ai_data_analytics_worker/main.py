"""Catalyst Job Function entry point for durable analytics tasks."""

import logging
from datetime import datetime, timedelta, timezone

import zcatalyst_sdk

from worker.dispatcher import dispatch_task
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
        task_table.update_row(
            {
                "ROWID": task_row["ROWID"],
                "status": "RUNNING",
                "attempt_count": int(task_row.get("attempt_count") or 0) + 1,
                "started_at": catalyst_datetime(now_utc),
                "lease_expires_at": catalyst_datetime(
                    now_utc + timedelta(minutes=10)
                ),
                "controlled_error_code": "",
            }
        )

        task_type = task_row.get("task_type")
        result = dispatch_task(app, task_row)

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
