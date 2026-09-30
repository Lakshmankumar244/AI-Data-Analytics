"""Continue a Salesforce extract from READY_TO_DOWNLOAD through scan COMPLETED.

Mirrors the Zoho ORCHESTRATE_SCAN tick: download results, PREPARE_BATCHES, then
PROCESS_BATCHES in the same worker invocation. Never POSTs a Bulk Query job.
"""

import importlib.util
import logging
from pathlib import Path

from salesforce.bulk_query import SalesforceBulkError
from salesforce.bulk_results import download_salesforce_query_results
from submit_bulk import _provider_job_id, _safe_result, _select_work
from task_resolve import SalesforceWorkerError, find_scan_modules
from tasks.prepare_batches import prepare_batches


def _load_process_and_finalize():
    path = Path(__file__).resolve().parent / "pipeline" / "processing.py"
    spec = importlib.util.spec_from_file_location(
        "ai_data_analytics_salesforce_worker_processing",
        path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.process_and_finalize


process_and_finalize = _load_process_and_finalize()
logger = logging.getLogger(__name__)

MAX_STEPS_PER_TICK = 40
RETRYABLE_DOWNLOAD_CODES = frozenset(
    {
        "SALESFORCE_BULK_RESULTS_FAILED",
        "TOKEN_REFRESH_FAILED",
        "BULK_EXPORT_FOLDER_NOT_CONFIGURED",
        "STRATUS_BUCKET_NOT_CONFIGURED",
        "FILESTORE_UPLOAD_FAILED",
    }
)


def _event_log(event, resolved, **fields):
    task = resolved.get("task") or {}
    parts = [event]
    payload = {
        "taskId": resolved.get("taskId") or task.get("task_id"),
        "scanId": resolved.get("scanId"),
        "pipeline_task_status": fields.pop(
            "pipeline_task_status", task.get("status")
        ),
        "provider_job_id": fields.pop("provider_job_id", None),
        "catalyst_job_id": fields.pop(
            "catalyst_job_id", task.get("catalyst_job_id")
        ),
        **fields,
    }
    for key, value in payload.items():
        if value not in (None, ""):
            parts.append(f"{key}={value}")
    logger.info(" ".join(str(part) for part in parts))


def _synthetic_batch_task(resolved, module_row, bulk_row):
    task_row = resolved.get("task") or {}
    return {
        "task_id": task_row.get("task_id"),
        "attempt_count": task_row.get("attempt_count") or 0,
        "status": "RUNNING",
        "scan_row_id": task_row.get("scan_row_id") or resolved["scan"].get("ROWID"),
        "scan_module_row_id": module_row.get("ROWID"),
        "bulk_job_row_id": bulk_row.get("ROWID"),
    }


def _mark_orchestrate_succeeded(app, resolved):
    task_row = resolved.get("task") or {}
    if not task_row.get("ROWID"):
        return
    from datetime import datetime, timezone

    app.datastore().table("pipeline_tasks").update_row(
        {
            "ROWID": task_row["ROWID"],
            "status": "SUCCEEDED",
            "completed_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "controlled_error_code": "",
        }
    )


def _scan_is_complete(zcql, scan_row):
    modules = find_scan_modules(zcql, scan_row.get("ROWID"))
    if not modules:
        return False
    return all(str(module.get("status") or "") == "COMPLETED" for module in modules)


def continue_salesforce_extract(app, resolved):
    """Download GET results and run Zoho-equivalent prepare/process steps."""
    scan_row = resolved["scan"]
    connection_row = resolved["connection"]
    zcql = app.zcql()
    datastore = app.datastore()
    last = None

    for _ in range(MAX_STEPS_PER_TICK):
        module_row, bulk_row, action = _select_work(zcql, scan_row)
        if action == "download":
            provider_job_id = _provider_job_id(bulk_row)
            _event_log(
                "SALESFORCE_RESULT_DOWNLOAD",
                resolved,
                provider_job_id=provider_job_id,
                method="GET",
                pipeline_task_status="RUNNING",
            )
            try:
                downloaded = download_salesforce_query_results(
                    datastore,
                    connection_row,
                    scan_row,
                    bulk_row,
                    module_row=module_row,
                    app=app,
                )
            except SalesforceBulkError as exc:
                retryable = exc.code in RETRYABLE_DOWNLOAD_CODES or exc.code not in {
                    "WRONG_CRM_PROVIDER",
                    "SCAN_NOT_OWNED",
                    "PROVIDER_JOB_ID_MISSING",
                    "BULK_JOB_STATE_CONFLICT",
                    "BULK_DOWNLOAD_RETRY_BLOCKED",
                    "BULK_EXPORT_TOO_LARGE",
                    "PROVIDER_JOB_NOT_FOUND",
                }
                _event_log(
                    "SALESFORCE_RESULT_DOWNLOAD_FAILED",
                    resolved,
                    provider_job_id=provider_job_id,
                    code=exc.code,
                    retryable=retryable,
                )
                if retryable:
                    return _safe_result(
                        outcome="DOWNLOAD_RETRYABLE",
                        taskId=resolved["taskId"],
                        scanId=resolved["scanId"],
                        crmProvider="salesforce",
                        module=module_row.get("module_api_name"),
                        bulkJobRowId=str(bulk_row.get("ROWID") or ""),
                        providerJobId=provider_job_id,
                        status="DOWNLOAD_RETRYABLE",
                        code=exc.code,
                        requeue=True,
                        retryAfterSeconds=30,
                    )
                raise SalesforceWorkerError(exc.code, str(exc)) from exc

            bulk_row.update(
                {
                    "status": "DOWNLOADED",
                    "source_file_key": downloaded.get("sourceFileKey"),
                    "source_file_name": downloaded.get("sourceFileName"),
                    "source_file_size": downloaded.get("sourceFileSize"),
                    "source_file_checksum": downloaded.get("sourceFileChecksum"),
                    "downloaded_record_count": downloaded.get("downloadedRecordCount"),
                }
            )
            module_row["status"] = "DOWNLOADED"
            _event_log(
                "SALESFORCE_RESULT_DOWNLOADED",
                resolved,
                provider_job_id=provider_job_id,
                recordsDownloaded=downloaded.get("downloadedRecordCount"),
                alreadyDownloaded=downloaded.get("alreadyDownloaded"),
            )
            last = _safe_result(
                outcome="DOWNLOADED",
                taskId=resolved["taskId"],
                scanId=resolved["scanId"],
                crmProvider="salesforce",
                module=module_row.get("module_api_name"),
                bulkJobRowId=str(bulk_row.get("ROWID") or ""),
                providerJobId=provider_job_id,
                status="DOWNLOADED",
                recordsDownloaded=downloaded.get("downloadedRecordCount"),
                alreadyDownloaded=downloaded.get("alreadyDownloaded"),
                requeue=False,
            )
            continue

        if action == "process":
            synthetic = _synthetic_batch_task(resolved, module_row, bulk_row)
            if str(bulk_row.get("status") or "") == "DOWNLOADED":
                _event_log(
                    "SALESFORCE_PREPARE_BATCHES",
                    resolved,
                    provider_job_id=_provider_job_id(bulk_row),
                    pipeline_task_status="RUNNING",
                )
                prepare_result = prepare_batches(app, synthetic)
            else:
                prepare_result = {"skipped": True, "reason": bulk_row.get("status")}
            _event_log(
                "SALESFORCE_PROCESS_BATCHES",
                resolved,
                provider_job_id=_provider_job_id(bulk_row),
                pipeline_task_status="RUNNING",
            )
            process_result = process_and_finalize(app, synthetic)
            last = _safe_result(
                outcome="PROCESSED",
                taskId=resolved["taskId"],
                scanId=resolved["scanId"],
                crmProvider="salesforce",
                module=module_row.get("module_api_name"),
                bulkJobRowId=str(bulk_row.get("ROWID") or ""),
                providerJobId=_provider_job_id(bulk_row),
                status="PROCESSED",
                recordsProcessed=process_result.get("recordCount"),
                batchCount=process_result.get("batchCount"),
                preparedBatches=prepare_result.get("batchCount"),
                requeue=False,
            )
            continue

        if action in {"poll", "submit"}:
            if last:
                last = dict(last)
                last["requeue"] = True
                last["retryAfterSeconds"] = int(last.get("retryAfterSeconds") or 0)
            return last
        if action == "blocked":
            return last or _safe_result(
                outcome="RETRY_BLOCKED",
                taskId=resolved["taskId"],
                scanId=resolved["scanId"],
                status=str((bulk_row or {}).get("status") or ""),
                requeue=False,
            )
        break

    if _scan_is_complete(zcql, scan_row):
        _mark_orchestrate_succeeded(app, resolved)
        _event_log(
            "SALESFORCE_SCAN_COMPLETED",
            resolved,
            provider_job_id=(last or {}).get("providerJobId"),
            pipeline_task_status="SUCCEEDED",
        )
        return _safe_result(
            outcome="COMPLETED",
            taskId=resolved["taskId"],
            scanId=resolved["scanId"],
            crmProvider="salesforce",
            status="COMPLETED",
            recordsProcessed=(last or {}).get("recordsProcessed"),
            recordsDownloaded=(last or {}).get("recordsDownloaded"),
            requeue=False,
        )
    return last
