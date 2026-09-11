"""Create deterministic 5,000-record processing checkpoints."""

import hashlib
import json
from datetime import datetime, timezone


from worker.profiler import ProfiledApp, ScanProfiler


BATCH_SIZE = 5000
BATCH_PLAN_VERSION = "batch-plan-v1"

def _canonical_hash(value):
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _catalyst_datetime(value):
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _foreign_row_id(value):
    if isinstance(value, dict):
        return value.get("ROWID") or value.get("rowid")
    return value


def _numeric_row_id(value, label):
    row_id = str(_foreign_row_id(value))
    if not row_id.isdigit():
        raise ValueError(f"{label} is invalid")
    return row_id


def _query_one(zcql, query, table_name):
    results = zcql.execute_query(query)
    return results[0][table_name] if results else None


def prepare_batches(app, task_row):
    profiler = ScanProfiler(
        "PREPARE_BATCHES",
        taskId=task_row.get("task_id"),
        attemptCount=int(task_row.get("attempt_count") or 0),
        priorStatus=task_row.get("status"),
    )
    app = ProfiledApp(app, profiler)
    datastore = app.datastore()
    zcql = app.zcql()
    bulk_row_id = _numeric_row_id(task_row.get("bulk_job_row_id"), "Bulk job link")
    bulk_row = _query_one(
        zcql,
        f"select * from bulk_read_jobs where ROWID = {bulk_row_id} limit 1",
        "bulk_read_jobs",
    )
    if not bulk_row:
        raise ValueError("Bulk Read job was not found")
    if bulk_row.get("status") not in {"DOWNLOADED", "PROCESSING_PLANNED"}:
        raise ValueError(
            f"Batches cannot be prepared from state {bulk_row.get('status')}"
        )

    module_row_id = _numeric_row_id(
        bulk_row.get("scan_module_row_id"), "Scan module link"
    )
    module_row = _query_one(
        zcql,
        f"select * from scan_module_runs where ROWID = {module_row_id} limit 1",
        "scan_module_runs",
    )
    if not module_row:
        raise ValueError("Scan module was not found")
    if str(_foreign_row_id(task_row.get("scan_module_row_id"))) != str(
        module_row["ROWID"]
    ):
        raise ValueError("Task module link does not match its Bulk Read job")

    expected_count = int(bulk_row.get("provider_record_count") or 0)
    if expected_count < 0:
        raise ValueError("Provider record count is invalid")
    source_checksum = bulk_row.get("source_file_checksum")
    if not bulk_row.get("source_file_id") or not source_checksum:
        raise ValueError("Downloaded source file metadata is incomplete")

    batch_table = datastore.table("processing_batches")
    batch_count = (expected_count + BATCH_SIZE - 1) // BATCH_SIZE
    created_count = 0
    with profiler.stage(
        "plan_batches",
        plannedBatches=batch_count,
        expectedRecordCount=expected_count,
    ):
        for batch_offset in range(batch_count):
            batch_number = batch_offset + 1
            start_index = batch_offset * BATCH_SIZE
            end_index = min(expected_count, start_index + BATCH_SIZE) - 1
            source_record_count = end_index - start_index + 1
            batch_key = _canonical_hash(
                {
                    "bulk_job_id": bulk_row["bulk_job_id"],
                    "source_checksum": source_checksum,
                    "batch_number": batch_number,
                    "start_record_index": start_index,
                    "end_record_index": end_index,
                    "version": BATCH_PLAN_VERSION,
                }
            )
            existing_batch = _query_one(
                zcql,
                f"select * from processing_batches where batch_key = '{batch_key}' limit 1",
                "processing_batches",
            )
            if existing_batch:
                if (
                    int(existing_batch["start_record_index"]) != start_index
                    or int(existing_batch["end_record_index"]) != end_index
                    or int(existing_batch["source_record_count"]) != source_record_count
                ):
                    raise ValueError("Existing processing batch does not match its plan")
                continue
            batch_table.insert_row(
                {
                    "batch_id": f"batch_{batch_key[:32]}",
                    "bulk_job_row_id": bulk_row["ROWID"],
                    "batch_key": batch_key,
                    "batch_number": batch_number,
                    "status": "PLANNED",
                    "start_record_index": start_index,
                    "end_record_index": end_index,
                    "source_record_count": source_record_count,
                    "processed_record_count": 0,
                    "attempt_count": 0,
                }
            )
            created_count += 1

    datastore.table("bulk_read_jobs").update_row(
        {
            "ROWID": bulk_row["ROWID"],
            "status": "PROCESSING_PLANNED",
            "controlled_error_code": "",
        }
    )
    datastore.table("scan_module_runs").update_row(
        {
            "ROWID": module_row["ROWID"],
            "status": "PROCESSING_PLANNED",
            "batches_completed": 0,
        }
    )
    profiler.meta["module"] = module_row.get("module_api_name")
    profiler.meta["expectedRecordCount"] = expected_count
    profiler.meta["batchCount"] = batch_count
    profiler.add("records_processed", expected_count)
    profile = profiler.summary()
    return {
        "batchCount": batch_count,
        "createdBatchCount": created_count,
        "scanProfile": profile,
    }
