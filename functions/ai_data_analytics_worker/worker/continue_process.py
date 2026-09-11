"""Continue from PREPARE_BATCHES into PROCESS_BATCHES in the same worker job."""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from pipeline.processing import process_and_finalize
from worker.task_state import catalyst_datetime, query_one


logger = logging.getLogger(__name__)

PROCESS_TASK_TYPE = "PROCESS_BATCHES"
AGGREGATE_SCHEMA_VERSION = "quality-aggregate-v1"
QUALITY_RULE_VERSION = "quality-rules-v1"


def _canonical_hash(value):
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _foreign_row_id(value):
    if isinstance(value, dict):
        return value.get("ROWID") or value.get("rowid")
    return value


def _numeric_row_id(value, label):
    row_id = str(_foreign_row_id(value))
    if not row_id.isdigit():
        raise ValueError(f"{label} is invalid")
    return row_id


def continue_to_process_batches(app, prepare_task_row):
    """Run PROCESS_BATCHES now if no other worker already owns that task."""
    zcql = app.zcql()
    datastore = app.datastore()
    bulk_row_id = _numeric_row_id(
        prepare_task_row.get("bulk_job_row_id"), "Bulk job link"
    )
    bulk_row = query_one(
        zcql,
        f"select * from bulk_read_jobs where ROWID = {bulk_row_id} limit 1",
        "bulk_read_jobs",
    )
    if not bulk_row:
        raise ValueError("Bulk Read job was not found")
    if bulk_row.get("status") == "PROCESSED":
        return {"skipped": True, "reason": "already_processed"}
    if bulk_row.get("status") not in {"PROCESSING_PLANNED", "PROCESSING"}:
        return {"skipped": True, "reason": str(bulk_row.get("status") or "")}

    task_key = _canonical_hash(
        {
            "task_type": PROCESS_TASK_TYPE,
            "bulk_job_id": bulk_row["bulk_job_id"],
            "source_file_checksum": bulk_row.get("source_file_checksum"),
            "aggregate_schema_version": AGGREGATE_SCHEMA_VERSION,
            "rule_version": QUALITY_RULE_VERSION,
        }
    )
    process_task = query_one(
        zcql,
        f"select * from pipeline_tasks where task_key = '{task_key}' limit 1",
        "pipeline_tasks",
    )
    task_table = datastore.table("pipeline_tasks")
    if process_task:
        status = str(process_task.get("status") or "")
        if status == "SUCCEEDED":
            return {
                "skipped": True,
                "reason": "process_task_succeeded",
                "taskId": process_task.get("task_id"),
            }
        if status in {"QUEUED", "RUNNING"}:
            logger.info(
                "PROCESS_BATCHES already %s for bulk %s; not starting a second run",
                status,
                bulk_row.get("bulk_job_id"),
            )
            return {
                "skipped": True,
                "reason": "process_task_active",
                "taskId": process_task.get("task_id"),
                "taskStatus": status,
            }
        if status == "OUTCOME_UNKNOWN":
            return {
                "skipped": True,
                "reason": "process_task_outcome_unknown",
                "taskId": process_task.get("task_id"),
            }
        if status not in {"PLANNED", "PAUSED_RETRYABLE"}:
            raise ValueError(f"PROCESS_BATCHES cannot continue from state {status}")
    else:
        process_task = task_table.insert_row(
            {
                "task_id": f"task_{uuid.uuid4().hex}",
                "task_key": task_key,
                "scan_row_id": prepare_task_row.get("scan_row_id"),
                "scan_module_row_id": prepare_task_row.get("scan_module_row_id"),
                "bulk_job_row_id": prepare_task_row.get("bulk_job_row_id"),
                "task_type": PROCESS_TASK_TYPE,
                "status": "PLANNED",
                "attempt_count": 0,
            }
        )

    now_utc = datetime.now(timezone.utc)
    task_table.update_row(
        {
            "ROWID": process_task["ROWID"],
            "status": "RUNNING",
            "attempt_count": int(process_task.get("attempt_count") or 0) + 1,
            "started_at": catalyst_datetime(now_utc),
            "lease_expires_at": catalyst_datetime(now_utc + timedelta(minutes=10)),
            "controlled_error_code": "",
        }
    )
    process_task = {
        **process_task,
        "status": "RUNNING",
        "attempt_count": int(process_task.get("attempt_count") or 0) + 1,
    }
    try:
        result = process_and_finalize(app, process_task)
    except Exception:
        try:
            task_table.update_row(
                {
                    "ROWID": process_task["ROWID"],
                    "status": "PAUSED_RETRYABLE",
                    "controlled_error_code": "PROCESS_BATCHES_FAILED",
                }
            )
        except Exception:
            logger.exception("Could not persist PROCESS_BATCHES failure")
        raise
    task_table.update_row(
        {
            "ROWID": process_task["ROWID"],
            "status": "SUCCEEDED",
            "completed_at": catalyst_datetime(datetime.now(timezone.utc)),
            "controlled_error_code": "",
        }
    )
    return {
        "skipped": False,
        "taskId": process_task.get("task_id"),
        "result": result,
    }
