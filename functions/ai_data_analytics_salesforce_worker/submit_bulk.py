"""Advance one Salesforce extract tick: submit or poll one Bulk Query job.

Polls an existing provider_job_id with GET /jobs/query/{id}. Never POSTs a
new Query job when provider_job_id is already stored. Does not download
results. SOQL is built only by salesforce.bulk_query.
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from salesforce.bulk_query import (
    SalesforceBulkError,
    build_salesforce_query_soql_from_plan,
    poll_salesforce_query_job,
    submit_salesforce_query_job,
)
from storage.locator import has_extract_locator
from task_resolve import (
    SalesforceWorkerError,
    find_bulk_jobs_for_module,
    find_scan_modules,
)


logger = logging.getLogger(__name__)

SUBMITTABLE_SCAN_STATUSES = frozenset({"CREATED", "PLANNED", "EXTRACTING"})
ALREADY_ACTIVE_BULK_STATUSES = frozenset(
    {
        "SUBMITTED",
        "PROCESSING",
        "READY_TO_DOWNLOAD",
        "DOWNLOAD_RETRYABLE",
        "DOWNLOADED",
        "PROCESSING_PLANNED",
        "PROCESSED",
    }
)
BLOCKED_RETRY_STATUSES = frozenset({"SUBMITTING", "SUBMISSION_UNKNOWN"})
DONE_POLL_STATUSES = frozenset(
    {
        "PROCESSED",
        "FAILED_TERMINAL",
    }
)
DOWNLOADABLE_BULK_STATUSES = frozenset({"READY_TO_DOWNLOAD", "DOWNLOAD_RETRYABLE"})
PROCESSABLE_BULK_STATUSES = frozenset({"DOWNLOADED", "PROCESSING_PLANNED"})
PRE_SUBMIT_ERROR_CODES = frozenset(
    {
        "TOKEN_REFRESH_FAILED",
        "REFRESH_TOKEN_MISSING",
        "SALESFORCE_OAUTH_CONFIG",
        "SALESFORCE_INSTANCE_MISSING",
        "INVALID_SOQL",
        "INVALID_FIELD_API_NAME",
        "INVALID_OBJECT_API_NAME",
        "INVALID_CLOCK_FIELD",
        "INVALID_FIELD_PLAN",
        "INVALID_SCAN_WINDOW",
        "CLOCK_FIELD_UNAVAILABLE",
    }
)
RETRYABLE_PRE_SUBMIT_CODES = frozenset(
    {
        "TOKEN_REFRESH_FAILED",
        "REFRESH_TOKEN_MISSING",
        "SALESFORCE_OAUTH_CONFIG",
        "SALESFORCE_INSTANCE_MISSING",
    }
)
BULK_STATUS_POLL_SECONDS = 30
POLL_BACKOFF_CAP_SECONDS = 120


def _canonical_hash(value):
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _catalyst_datetime(now=None):
    value = now or datetime.now(timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _provider_job_id(bulk_row):
    return str((bulk_row or {}).get("provider_job_id") or "").strip()


def _safe_result(**fields):
    return {key: value for key, value in fields.items() if value is not None}


def _parse_catalyst_datetime(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text = str(value or "").strip()
    if not text:
        raise ValueError("empty datetime")
    for date_format in (
        "%Y-%m-%d %H:%M:%S:%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
    ):
        try:
            return datetime.strptime(text, date_format).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _poll_backoff_seconds(bulk_row):
    raw = (bulk_row or {}).get("submitted_at")
    if not raw:
        return BULK_STATUS_POLL_SECONDS
    try:
        started = _parse_catalyst_datetime(raw)
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    except (TypeError, ValueError):
        return BULK_STATUS_POLL_SECONDS
    if elapsed < 90:
        return 30
    if elapsed < 240:
        return 60
    return POLL_BACKOFF_CAP_SECONDS


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


def _seconds_until_retry(bulk_row):
    value = (bulk_row or {}).get("next_retry_at")
    if not value:
        return 0
    try:
        retry_at = _parse_catalyst_datetime(value)
    except (TypeError, ValueError):
        return 0
    remaining = int((retry_at - datetime.now(timezone.utc)).total_seconds())
    return remaining if remaining > 0 else 0


def _select_work(zcql, scan_row):
    modules = find_scan_modules(zcql, scan_row.get("ROWID"))
    if not modules:
        raise SalesforceWorkerError(
            "MODULE_PLAN_MISSING",
            "The Salesforce scan has no module plans",
        )
    blocked = None
    for module_row in modules:
        bulk_jobs = find_bulk_jobs_for_module(zcql, module_row.get("ROWID"))
        poll_row = None
        planned = None
        blocking = None
        for bulk_row in bulk_jobs:
            status = str(bulk_row.get("status") or "")
            if _provider_job_id(bulk_row):
                if status in DOWNLOADABLE_BULK_STATUSES or (
                    status == "DOWNLOAD_UNKNOWN" and not has_extract_locator(bulk_row)
                ):
                    return module_row, bulk_row, "download"
                if status in PROCESSABLE_BULK_STATUSES or (
                    status == "PROCESSING" and has_extract_locator(bulk_row)
                ):
                    return module_row, bulk_row, "process"
                if status in {"DOWNLOADING", "DOWNLOAD_UNKNOWN"}:
                    if blocked is None:
                        blocked = (module_row, bulk_row)
                    continue
                if status in DONE_POLL_STATUSES:
                    continue
                poll_row = bulk_row
                break
            if status in BLOCKED_RETRY_STATUSES or status in ALREADY_ACTIVE_BULK_STATUSES:
                blocking = bulk_row
            elif status == "PLANNED" or not status:
                planned = bulk_row
        if poll_row:
            return module_row, poll_row, "poll"
        if blocking:
            if blocked is None:
                blocked = (module_row, blocking)
            continue
        if planned is not None or not bulk_jobs:
            return module_row, planned, "submit"
    if blocked:
        return blocked[0], blocked[1], "blocked"
    return None, None, "all_done"


def _ensure_planned_bulk_row(datastore, zcql, scan_row, module_row, existing):
    if existing:
        return existing
    logical_job_key = _canonical_hash(
        {
            "crm_provider": "salesforce",
            "scan_id": scan_row.get("scan_id"),
            "scan_module_id": module_row.get("scan_module_id"),
            "field_plan_hash": module_row.get("field_plan_hash"),
            "criteria_hash": module_row.get("criteria_hash"),
            "page": 1,
        }
    )
    existing_rows = find_bulk_jobs_for_module(zcql, module_row.get("ROWID"))
    for bulk_row in existing_rows:
        if str(bulk_row.get("logical_job_key") or "") == logical_job_key:
            return bulk_row
        if _provider_job_id(bulk_row) or str(bulk_row.get("status") or "") in (
            BLOCKED_RETRY_STATUSES | ALREADY_ACTIVE_BULK_STATUSES
        ):
            return bulk_row
    return datastore.table("bulk_read_jobs").insert_row(
        {
            "bulk_job_id": f"bulk_{uuid.uuid4().hex}",
            "scan_module_row_id": module_row["ROWID"],
            "logical_job_key": logical_job_key,
            "provider_page": 1,
            "status": "PLANNED",
            "attempt_count": 0,
            "downloaded_record_count": 0,
        }
    )


def _mark_bulk(datastore, bulk_row, **fields):
    update = {"ROWID": bulk_row["ROWID"], **fields}
    if "zoho_job_id" in update:
        raise RuntimeError("Salesforce submit must not write zoho_job_id")
    datastore.table("bulk_read_jobs").update_row(update)
    bulk_row.update(update)
    return bulk_row


def submit_one_salesforce_bulk_job(app, resolved):
    """Submit or poll at most one Salesforce Query job for the resolved scan."""
    scan_row = resolved["scan"]
    connection_row = resolved["connection"]
    task_row = resolved["task"]
    zcql = app.zcql()
    datastore = app.datastore()

    scan_status = str(scan_row.get("status") or "")
    if scan_status not in SUBMITTABLE_SCAN_STATUSES:
        raise SalesforceWorkerError(
            "SCAN_STATE_CONFLICT",
            f"Salesforce Bulk job cannot be submitted from state {scan_status}",
        )

    module_row, bulk_row, action = _select_work(zcql, scan_row)
    if action == "all_done":
        logger.info(
            "Salesforce worker extract has no remaining submit/poll work taskId=%s "
            "scanId=%s crm_provider=salesforce",
            resolved["taskId"],
            resolved["scanId"],
        )
        return _safe_result(
            outcome="WAITING_FOR_DOWNLOAD",
            taskId=resolved["taskId"],
            scanId=resolved["scanId"],
            crmProvider="salesforce",
            status="READY_TO_DOWNLOAD",
            requeue=False,
        )
    if action == "download":
        return _safe_result(
            outcome="READY_TO_DOWNLOAD",
            taskId=resolved["taskId"],
            scanId=resolved["scanId"],
            crmProvider="salesforce",
            module=module_row.get("module_api_name"),
            bulkJobRowId=str(bulk_row.get("ROWID") or ""),
            providerJobId=_provider_job_id(bulk_row),
            status=str(bulk_row.get("status") or "READY_TO_DOWNLOAD"),
            requeue=False,
        )
    if action == "process":
        return _safe_result(
            outcome="PROCESS_NEEDED",
            taskId=resolved["taskId"],
            scanId=resolved["scanId"],
            crmProvider="salesforce",
            module=module_row.get("module_api_name"),
            bulkJobRowId=str(bulk_row.get("ROWID") or ""),
            providerJobId=_provider_job_id(bulk_row),
            status=str(bulk_row.get("status") or "DOWNLOADED"),
            requeue=False,
        )
    if action == "blocked":
        logger.info(
            "Salesforce worker submission retry blocked taskId=%s scanId=%s "
            "module=%s bulkRowId=%s status=%s",
            resolved["taskId"],
            resolved["scanId"],
            module_row.get("module_api_name"),
            bulk_row.get("ROWID"),
            bulk_row.get("status"),
        )
        return _safe_result(
            outcome="SUBMISSION_UNKNOWN"
            if str(bulk_row.get("status") or "") == "SUBMISSION_UNKNOWN"
            else "RETRY_BLOCKED",
            taskId=resolved["taskId"],
            scanId=resolved["scanId"],
            crmProvider="salesforce",
            module=module_row.get("module_api_name"),
            bulkJobRowId=str(bulk_row.get("ROWID") or ""),
            status=bulk_row.get("status"),
            requeue=False,
        )
    if action == "poll":
        return _poll_existing_salesforce_job(
            datastore, resolved, module_row, bulk_row, connection_row, task_row
        )

    bulk_row = _ensure_planned_bulk_row(
        datastore, zcql, scan_row, module_row, bulk_row
    )
    if _provider_job_id(bulk_row):
        logger.info(
            "Salesforce worker routing existing job to poll taskId=%s scanId=%s "
            "module=%s bulkRowId=%s providerJobId=%s status=%s",
            resolved["taskId"],
            resolved["scanId"],
            module_row.get("module_api_name"),
            bulk_row.get("ROWID"),
            _provider_job_id(bulk_row),
            bulk_row.get("status"),
        )
        return _poll_existing_salesforce_job(
            datastore, resolved, module_row, bulk_row, connection_row, task_row
        )

    return _submit_new_salesforce_job(
        datastore, resolved, scan_row, module_row, bulk_row, connection_row, task_row
    )


def _poll_existing_salesforce_job(
    datastore, resolved, module_row, bulk_row, connection_row, task_row
):
    scan_row = resolved["scan"]
    provider_job_id = _provider_job_id(bulk_row)
    if not provider_job_id:
        raise SalesforceWorkerError(
            "PROVIDER_JOB_ID_MISSING",
            "Salesforce poll requires an existing provider_job_id",
        )

    wait_seconds = _seconds_until_retry(bulk_row)
    if wait_seconds > 0:
        _event_log(
            "SALESFORCE_PROVIDER_PROCESSING",
            resolved,
            provider_job_id=provider_job_id,
            pipeline_task_status=task_row.get("status"),
            reason="next_retry_at",
            retryAfterSeconds=wait_seconds,
        )
        return _safe_result(
            outcome="POLL_WAITING",
            taskId=resolved["taskId"],
            scanId=resolved["scanId"],
            crmProvider="salesforce",
            module=module_row.get("module_api_name"),
            bulkJobRowId=str(bulk_row.get("ROWID") or ""),
            providerJobId=provider_job_id,
            status=str(bulk_row.get("status") or "PROCESSING"),
            retryAfterSeconds=wait_seconds,
            reason="next_retry_at",
            requeue=True,
        )

    _event_log(
        "SALESFORCE_PROVIDER_POLL",
        resolved,
        provider_job_id=provider_job_id,
        pipeline_task_status=task_row.get("status"),
        method="GET",
    )
    try:
        job = poll_salesforce_query_job(
            datastore,
            connection_row,
            provider_job_id,
            bulk_row=None,
        )
    except SalesforceBulkError as exc:
        return _handle_poll_error(resolved, module_row, bulk_row, exc)

    status = str(job.get("internalStatus") or "")
    processed = job.get("numberRecordsProcessed")
    provider_state = str(job.get("state") or "")

    if status in {"SUBMITTED", "PROCESSING"}:
        retry_after = _poll_backoff_seconds(bulk_row)
        next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=retry_after)
        persist_fields = {
            "provider_job_id": provider_job_id,
            "status": status,
            "next_retry_at": _catalyst_datetime(next_retry_at),
            "controlled_error_code": "",
        }
        if processed is not None:
            persist_fields["provider_record_count"] = processed
        _mark_bulk(datastore, bulk_row, **persist_fields)
        datastore.table("scan_module_runs").update_row(
            {"ROWID": module_row["ROWID"], "status": status}
        )
        datastore.table("scan_jobs").update_row(
            {
                "ROWID": scan_row["ROWID"],
                "status": "EXTRACTING",
                "controlled_error_code": "",
            }
        )
        _event_log(
            "SALESFORCE_PROVIDER_PROCESSING",
            resolved,
            provider_job_id=provider_job_id,
            pipeline_task_status=task_row.get("status"),
            providerState=provider_state,
            status=status,
            retryAfterSeconds=retry_after,
        )
        return _safe_result(
            outcome="POLL_WAITING",
            taskId=resolved["taskId"],
            scanId=resolved["scanId"],
            crmProvider="salesforce",
            module=module_row.get("module_api_name"),
            bulkJobRowId=str(bulk_row.get("ROWID") or ""),
            providerJobId=provider_job_id,
            status=status,
            providerState=provider_state,
            providerRecordCount=processed,
            retryAfterSeconds=retry_after,
            nextRetryAt=_catalyst_datetime(next_retry_at),
            reason="provider_processing",
            requeue=True,
        )

    if status == "READY_TO_DOWNLOAD":
        persist_fields = {
            "provider_job_id": provider_job_id,
            "status": "READY_TO_DOWNLOAD",
            "provider_completed_at": _catalyst_datetime(),
            "controlled_error_code": "",
        }
        if processed is not None:
            persist_fields["provider_record_count"] = processed
        _mark_bulk(datastore, bulk_row, **persist_fields)
        module_update = {
            "ROWID": module_row["ROWID"],
            "status": "READY_TO_DOWNLOAD",
        }
        if processed is not None:
            module_update["expected_record_count"] = processed
        datastore.table("scan_module_runs").update_row(module_update)
        datastore.table("scan_jobs").update_row(
            {
                "ROWID": scan_row["ROWID"],
                "status": "EXTRACTING",
                "controlled_error_code": "",
            }
        )
        datastore.table("pipeline_tasks").update_row(
            {
                "ROWID": task_row["ROWID"],
                "status": "PLANNED",
                "controlled_error_code": "",
            }
        )
        _event_log(
            "SALESFORCE_PROVIDER_COMPLETE",
            resolved,
            provider_job_id=provider_job_id,
            pipeline_task_status="PLANNED",
            status="READY_TO_DOWNLOAD",
            providerState=provider_state,
        )
        return _safe_result(
            outcome="READY_TO_DOWNLOAD",
            taskId=resolved["taskId"],
            scanId=resolved["scanId"],
            crmProvider="salesforce",
            module=module_row.get("module_api_name"),
            bulkJobRowId=str(bulk_row.get("ROWID") or ""),
            providerJobId=provider_job_id,
            status="READY_TO_DOWNLOAD",
            providerState=provider_state,
            providerRecordCount=processed,
            requeue=False,
        )

    error_code = (
        str(job.get("errorMessage") or "").strip()[:100]
        or (
            "SALESFORCE_BULK_JOB_ABORTED"
            if provider_state == "Aborted"
            else "SALESFORCE_BULK_JOB_FAILED"
        )
    )
    persist_fields = {
        "provider_job_id": provider_job_id,
        "status": "FAILED_TERMINAL",
        "controlled_error_code": error_code,
        "provider_completed_at": _catalyst_datetime(),
    }
    if processed is not None:
        persist_fields["provider_record_count"] = processed
    _mark_bulk(datastore, bulk_row, **persist_fields)
    datastore.table("scan_module_runs").update_row(
        {"ROWID": module_row["ROWID"], "status": "FAILED_TERMINAL"}
    )
    datastore.table("scan_jobs").update_row(
        {
            "ROWID": scan_row["ROWID"],
            "status": "PAUSED_RETRYABLE",
            "controlled_error_code": error_code[:100],
        }
    )
    datastore.table("pipeline_tasks").update_row(
        {
            "ROWID": task_row["ROWID"],
            "status": "PLANNED",
            "controlled_error_code": error_code[:100],
        }
    )
    _event_log(
        "SALESFORCE_PROVIDER_FAILED",
        resolved,
        provider_job_id=provider_job_id,
        pipeline_task_status="PLANNED",
        providerState=provider_state,
        status="FAILED_TERMINAL",
        code=error_code,
    )
    return _safe_result(
        outcome="FAILED_TERMINAL",
        taskId=resolved["taskId"],
        scanId=resolved["scanId"],
        crmProvider="salesforce",
        module=module_row.get("module_api_name"),
        bulkJobRowId=str(bulk_row.get("ROWID") or ""),
        providerJobId=provider_job_id,
        status="FAILED_TERMINAL",
        providerState=provider_state,
        providerRecordCount=processed,
        code=error_code,
        requeue=False,
    )


def _submit_new_salesforce_job(
    datastore, resolved, scan_row, module_row, bulk_row, connection_row, task_row
):
    build_salesforce_query_soql_from_plan(scan_row, module_row)
    try:
        fields = json.loads(module_row.get("field_allowlist_json") or "[]")
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SalesforceBulkError(
            "INVALID_FIELD_PLAN",
            "The stored Salesforce field allowlist is invalid",
        ) from exc

    try:
        attempt_count = int(bulk_row.get("attempt_count") or 0) + 1
        _mark_bulk(
            datastore,
            bulk_row,
            status="SUBMITTING",
            attempt_count=attempt_count,
            submitted_at=_catalyst_datetime(),
            controlled_error_code="",
        )
    except Exception as exc:
        logger.exception(
            "Could not lock Salesforce bulk row taskId=%s scanId=%s bulkRowId=%s",
            resolved["taskId"],
            resolved["scanId"],
            bulk_row.get("ROWID"),
        )
        raise SalesforceWorkerError(
            "BULK_SUBMISSION_LOCK_FAILED",
            "Salesforce Bulk submission was not started",
        ) from exc

    try:
        job = submit_salesforce_query_job(
            datastore,
            connection_row,
            module_row.get("module_api_name"),
            fields,
            scan_row.get("clock_field"),
            scan_row.get("from_utc"),
            scan_row.get("to_utc"),
            bulk_row=None,
        )
    except SalesforceBulkError as exc:
        return _handle_submit_error(
            datastore, resolved, module_row, bulk_row, exc
        )

    provider_job_id = str((job or {}).get("id") or "").strip()
    if not provider_job_id:
        _mark_bulk(
            datastore,
            bulk_row,
            status="SUBMISSION_UNKNOWN",
            controlled_error_code="SALESFORCE_JOB_RESPONSE_INVALID",
        )
        logger.info(
            "Salesforce worker submission unknown taskId=%s scanId=%s "
            "module=%s bulkRowId=%s status=SUBMISSION_UNKNOWN",
            resolved["taskId"],
            resolved["scanId"],
            module_row.get("module_api_name"),
            bulk_row.get("ROWID"),
        )
        return _safe_result(
            outcome="SUBMISSION_UNKNOWN",
            taskId=resolved["taskId"],
            scanId=resolved["scanId"],
            crmProvider="salesforce",
            module=module_row.get("module_api_name"),
            bulkJobRowId=str(bulk_row.get("ROWID") or ""),
            status="SUBMISSION_UNKNOWN",
            requeue=False,
        )

    next_retry_at = datetime.now(timezone.utc) + timedelta(
        seconds=BULK_STATUS_POLL_SECONDS
    )
    try:
        _mark_bulk(
            datastore,
            bulk_row,
            provider_job_id=provider_job_id,
            status="SUBMITTED",
            next_retry_at=_catalyst_datetime(next_retry_at),
            controlled_error_code="",
        )
        datastore.table("scan_module_runs").update_row(
            {"ROWID": module_row["ROWID"], "status": "SUBMITTED", "bulk_jobs_planned": 1}
        )
        datastore.table("scan_jobs").update_row(
            {
                "ROWID": scan_row["ROWID"],
                "status": "EXTRACTING",
                "controlled_error_code": "",
            }
        )
        datastore.table("pipeline_tasks").update_row(
            {
                "ROWID": task_row["ROWID"],
                "status": "PLANNED",
                "controlled_error_code": "",
            }
        )
    except Exception:
        logger.exception(
            "Salesforce job exists but local persistence failed taskId=%s "
            "scanId=%s module=%s bulkRowId=%s providerJobId=%s",
            resolved["taskId"],
            resolved["scanId"],
            module_row.get("module_api_name"),
            bulk_row.get("ROWID"),
            provider_job_id,
        )
        try:
            _mark_bulk(
                datastore,
                bulk_row,
                provider_job_id=provider_job_id,
                status="SUBMISSION_UNKNOWN",
                controlled_error_code="SALESFORCE_JOB_PERSIST_FAILED",
            )
        except Exception:
            logger.exception(
                "Could not mark Salesforce bulk row unknown taskId=%s bulkRowId=%s",
                resolved["taskId"],
                bulk_row.get("ROWID"),
            )
        return _safe_result(
            outcome="SUBMISSION_UNKNOWN",
            taskId=resolved["taskId"],
            scanId=resolved["scanId"],
            crmProvider="salesforce",
            module=module_row.get("module_api_name"),
            bulkJobRowId=str(bulk_row.get("ROWID") or ""),
            providerJobId=provider_job_id,
            status="SUBMISSION_UNKNOWN",
            requeue=False,
        )

    logger.info(
        "Salesforce worker submitted taskId=%s scanId=%s module=%s "
        "bulkRowId=%s providerJobId=%s status=SUBMITTED crm_provider=salesforce",
        resolved["taskId"],
        resolved["scanId"],
        module_row.get("module_api_name"),
        bulk_row.get("ROWID"),
        provider_job_id,
    )
    return _safe_result(
        outcome="SUBMITTED",
        taskId=resolved["taskId"],
        scanId=resolved["scanId"],
        crmProvider="salesforce",
        module=module_row.get("module_api_name"),
        bulkJobRowId=str(bulk_row.get("ROWID") or ""),
        providerJobId=provider_job_id,
        status="SUBMITTED",
        retryAfterSeconds=BULK_STATUS_POLL_SECONDS,
        reason="provider_processing",
        requeue=True,
    )


def _handle_poll_error(resolved, module_row, bulk_row, exc):
    code = getattr(exc, "code", "") or "SALESFORCE_BULK_QUERY_FAILED"
    if code in RETRYABLE_PRE_SUBMIT_CODES:
        logger.info(
            "Salesforce worker poll retryable failure taskId=%s scanId=%s "
            "module=%s bulkRowId=%s providerJobId=%s code=%s",
            resolved["taskId"],
            resolved["scanId"],
            module_row.get("module_api_name"),
            bulk_row.get("ROWID"),
            _provider_job_id(bulk_row),
            code,
        )
        raise SalesforceWorkerError(code, str(exc)) from exc

    logger.info(
        "Salesforce worker poll failed taskId=%s scanId=%s module=%s "
        "bulkRowId=%s providerJobId=%s code=%s",
        resolved["taskId"],
        resolved["scanId"],
        module_row.get("module_api_name"),
        bulk_row.get("ROWID"),
        _provider_job_id(bulk_row),
        code,
    )
    raise SalesforceWorkerError(code, str(exc)) from exc


def _handle_submit_error(datastore, resolved, module_row, bulk_row, exc):
    code = getattr(exc, "code", "") or "SALESFORCE_BULK_QUERY_FAILED"
    if code in PRE_SUBMIT_ERROR_CODES:
        status = (
            "PAUSED_RETRYABLE" if code in RETRYABLE_PRE_SUBMIT_CODES else "FAILED_TERMINAL"
        )
        _mark_bulk(
            datastore,
            bulk_row,
            status=status,
            controlled_error_code=code[:100],
        )
        logger.info(
            "Salesforce worker submit failed before job create taskId=%s scanId=%s "
            "module=%s bulkRowId=%s status=%s",
            resolved["taskId"],
            resolved["scanId"],
            module_row.get("module_api_name"),
            bulk_row.get("ROWID"),
            status,
        )
        raise SalesforceWorkerError(code, str(exc)) from exc

    _mark_bulk(
        datastore,
        bulk_row,
        status="SUBMISSION_UNKNOWN",
        controlled_error_code=(code or "SALESFORCE_SUBMISSION_OUTCOME_UNKNOWN")[:100],
    )
    logger.info(
        "Salesforce worker submission unknown taskId=%s scanId=%s module=%s "
        "bulkRowId=%s status=SUBMISSION_UNKNOWN",
        resolved["taskId"],
        resolved["scanId"],
        module_row.get("module_api_name"),
        bulk_row.get("ROWID"),
    )
    return _safe_result(
        outcome="SUBMISSION_UNKNOWN",
        taskId=resolved["taskId"],
        scanId=resolved["scanId"],
        crmProvider="salesforce",
        module=module_row.get("module_api_name"),
        bulkJobRowId=str(bulk_row.get("ROWID") or ""),
        status="SUBMISSION_UNKNOWN",
        requeue=False,
    )
