"""Build stable API representations from analytics datastore rows."""

import json

from common.core import foreign_row_id


class StoredAnalyticsError(RuntimeError):
    """Raised when a persisted aggregate cannot be represented safely."""


def _integer(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def build_status(scan_row, module_rows, bulk_jobs_by_module, batches_by_bulk, tasks):
    tasks_by_module = {}
    for task in tasks:
        module_row_id = str(foreign_row_id(task.get("scan_module_row_id")) or "")
        tasks_by_module.setdefault(module_row_id, []).append(task)

    modules = []
    for module_row in sorted(
        module_rows, key=lambda row: int(row.get("ROWID") or 0)
    ):
        module_row_id = str(module_row["ROWID"])
        bulk_jobs = bulk_jobs_by_module.get(module_row_id, [])
        batch_rows = [
            batch
            for bulk_job in bulk_jobs
            for batch in batches_by_bulk.get(str(bulk_job["ROWID"]), [])
        ]
        batch_status_counts = {}
        for batch in batch_rows:
            status = str(batch.get("status") or "UNKNOWN")
            batch_status_counts[status] = batch_status_counts.get(status, 0) + 1
        processed_from_batches = sum(
            _integer(batch.get("processed_record_count"))
            for batch in batch_rows
            if str(batch.get("status") or "") == "COMPLETED"
        )
        completed_batch_count = batch_status_counts.get("COMPLETED", 0)

        modules.append(
            {
                "moduleApiName": module_row.get("module_api_name"),
                "status": module_row.get("status"),
                "expectedRecordCount": _integer(
                    module_row.get("expected_record_count")
                ),
                "recordsDownloaded": _integer(module_row.get("records_downloaded")),
                "recordsProcessed": max(
                    _integer(module_row.get("records_processed")),
                    processed_from_batches,
                ),
                "batchesCompleted": max(
                    _integer(module_row.get("batches_completed")),
                    completed_batch_count,
                ),
                "batches": {
                    "total": len(batch_rows),
                    "byStatus": batch_status_counts,
                },
                "bulkJobs": [
                    {
                        "bulkJobId": bulk_job.get("bulk_job_id"),
                        "status": bulk_job.get("status"),
                        "providerRecordCount": _integer(
                            bulk_job.get("provider_record_count")
                        ),
                    }
                    for bulk_job in bulk_jobs
                ],
                "tasks": [
                    {
                        "taskId": task.get("task_id"),
                        "taskType": task.get("task_type"),
                        "status": task.get("status"),
                        "attemptCount": _integer(task.get("attempt_count")),
                        "controlledErrorCode": task.get("controlled_error_code") or None,
                    }
                    for task in tasks_by_module.get(module_row_id, [])
                ],
            }
        )

    return {
        "scanId": scan_row.get("scan_id"),
        "status": scan_row.get("status"),
        "plannedModuleCount": _integer(scan_row.get("planned_module_count")),
        "completedModuleCount": _integer(scan_row.get("completed_module_count")),
        "modules": modules,
    }


def build_results(scan_row, result_rows):
    modules = {}
    preferred_owner_schema = {}
    for row in result_rows:
        if (
            row.get("status") == "COMPUTED"
            and str(row.get("result_scope") or "").upper() == "OWNER"
        ):
            module_name = str(row.get("module_api_name") or "")
            schema_version = str(row.get("schema_version") or "")
            preferred_owner_schema[module_name] = max(
                preferred_owner_schema.get(module_name, ""), schema_version
            )
    for row in result_rows:
        if row.get("status") != "COMPUTED":
            continue
        aggregate_json = row.get("aggregate_json")
        try:
            aggregate = json.loads(aggregate_json)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise StoredAnalyticsError(
                f"Stored aggregate {row.get('result_id')} is invalid"
            ) from exc
        if not isinstance(aggregate, dict):
            raise StoredAnalyticsError(
                f"Stored aggregate {row.get('result_id')} is not an object"
            )

        module_name = str(row.get("module_api_name") or "")
        metric_group = str(row.get("metric_group") or "")
        if not module_name or not metric_group:
            raise StoredAnalyticsError("Stored analytics result identity is incomplete")

        module = modules.setdefault(
            module_name,
            {
                "moduleApiName": module_name,
                "sourceRecordCount": 0,
                "metrics": {},
                "_owners": {},
            },
        )
        candidate = {
            "schemaVersion": row.get("schema_version"),
            "ruleVersion": row.get("rule_version"),
            "resultChecksum": row.get("result_checksum"),
            "computedAt": str(row.get("computed_at") or ""),
            "data": aggregate,
        }
        if str(row.get("result_scope") or "MODULE").upper() == "OWNER":
            if str(row.get("schema_version") or "") != preferred_owner_schema.get(
                module_name, ""
            ):
                continue
            owner_key = str(aggregate.get("ownerKey") or "")
            if not owner_key:
                raise StoredAnalyticsError("Stored owner analytics identity is incomplete")
            existing_owner = module["_owners"].get(owner_key)
            if existing_owner is None or candidate["computedAt"] >= existing_owner["computedAt"]:
                module["_owners"][owner_key] = candidate
            continue

        existing = module["metrics"].get(metric_group)
        if existing is None or candidate["computedAt"] >= existing["computedAt"]:
            module["metrics"][metric_group] = candidate
            module["sourceRecordCount"] = _integer(row.get("source_record_count"))

    output_modules = []
    for name in sorted(modules):
        module = modules[name]
        owners = module.pop("_owners")
        module["ownerAnalytics"] = [
            owners[key] for key in sorted(
                owners,
                key=lambda owner_key: (
                    str(owners[owner_key]["data"].get("ownerName") or "").lower(),
                    owner_key,
                ),
            )
        ]
        output_modules.append(module)

    return {
        "scanId": scan_row.get("scan_id"),
        "status": scan_row.get("status"),
        "modules": output_modules,
    }
