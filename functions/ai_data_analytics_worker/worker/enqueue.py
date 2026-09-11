"""Submit ORCHESTRATE_SCAN ticks to the existing Catalyst worker pool."""

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone

LOGGER = logging.getLogger(__name__)

ORCHESTRATE_TASK_TYPE = "ORCHESTRATE_SCAN"


def _canonical_hash(value):
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _job_identifier(job_response):
    if not isinstance(job_response, dict):
        return None
    for key in ("id", "job_id", "jobId", "JOBID"):
        value = job_response.get(key)
        if value is not None:
            return str(value)
    return None


def _catalyst_datetime_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _worker_target():
    pool_name = os.environ.get("ANALYTICS_WORKER_JOB_POOL_NAME", "")
    function_name = os.environ.get("ANALYTICS_WORKER_FUNCTION_NAME", "")
    return pool_name, function_name


def submit_orchestrate_job(app, task_id, delay_seconds=0):
    """Enqueue the next tick without sleeping in this invocation."""
    pool_name, function_name = _worker_target()
    if not pool_name or not function_name:
        raise RuntimeError("ANALYTICS_WORKER_NOT_CONFIGURED")

    delay = max(0, int(delay_seconds or 0))
    job_name = f"ada_{_canonical_hash(f'{task_id}:{time.time_ns()}:{delay}')[:16]}"
    job_payload = {
        "job_name": job_name,
        "jobpool_name": pool_name,
        "target_type": "Function",
        "target_name": function_name,
        "params": {"taskId": task_id},
    }
    delayed = False
    if delay > 0:
        try:
            job_response = _submit_delayed_job(app, job_payload, delay)
            delayed = True
            return job_response, delayed, _job_identifier(job_response)
        except Exception:
            LOGGER.exception(
                "ORCHESTRATE_SCAN delayed enqueue fell back to immediate submit task_id=%s delay=%s",
                task_id,
                delay,
            )
    job_response = app.job_scheduling().job.submit_job(job_payload)
    return job_response, delayed, _job_identifier(job_response)


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


def mark_orchestrate_queued(datastore, task_row):
    datastore.table("pipeline_tasks").update_row(
        {
            "ROWID": task_row["ROWID"],
            "status": "QUEUED",
            "enqueued_at": _catalyst_datetime_now(),
            "controlled_error_code": "",
        }
    )
