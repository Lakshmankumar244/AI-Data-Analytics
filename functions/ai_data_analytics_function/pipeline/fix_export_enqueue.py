"""Enqueue EXPORT_FIX_XLSX without hydrating findings or generating XLSX."""

import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone

from analytics.fix_records import FIX_SCHEMA_VERSION, _module_kpis
from analytics.repository import find_analytics_results, find_owned_scan
from common.core import AuthenticationRequired, get_current_user_id, json_response
from connections.repository import scan_crm_provider
from pipeline.shared import (
    canonical_hash,
    catalyst_datetime_now,
    catalyst_error_details,
    job_identifier,
)


LOGGER = logging.getLogger(__name__)
EXPORT_TASK_TYPE = "EXPORT_FIX_XLSX"
EXPORT_VERSION = "fix-export-v1"
ALLOWED_SEVERITIES = frozenset({"LOW", "MEDIUM", "HIGH", "CRITICAL"})
QUEUED_STARTUP_GRACE_SECONDS = 10 * 60
ACTIVE_EXPORT_STATES = frozenset({"QUEUED", "RUNNING"})
RESTARTABLE_EXPORT_STATES = frozenset({"PLANNED", "PAUSED_RETRYABLE"})


def _error(code, message, status):
    return json_response({"error": {"code": code, "message": message}}, status)


def _sql_string(value):
    return str(value or "").replace("'", "''")


def normalize_fix_export_request(payload):
    source = payload if isinstance(payload, dict) else {}
    module = str(source.get("module") or "").strip()
    q = str(source.get("q") or "").strip()[:100]
    owners_raw = source.get("owners")
    if owners_raw is None and source.get("owner"):
        owners_raw = [source.get("owner")]
    if not isinstance(owners_raw, list):
        owners_raw = []
    owners = []
    seen = set()
    for item in owners_raw:
        token = str(item or "").strip()
        if not token or token in seen or len(token) > 80:
            continue
        seen.add(token)
        owners.append(token)
    owners.sort()
    severity = str(source.get("severity") or "").strip().upper()
    if severity not in ALLOWED_SEVERITIES:
        severity = ""
    issue_type = re.sub(r"[^A-Z0-9_]", "", str(source.get("issueType") or "").strip().upper())
    return {
        "module": module,
        "q": q,
        "owners": owners,
        "severity": severity,
        "issueType": issue_type,
        "schemaVersion": FIX_SCHEMA_VERSION,
        "version": EXPORT_VERSION,
    }


def fix_export_task_key(scan_id, request):
    return canonical_hash(
        {
            "task_type": EXPORT_TASK_TYPE,
            "scan_id": scan_id,
            "request": request,
        }
    )


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


def queued_is_stale(task_row, now=None):
    if str((task_row or {}).get("status") or "") != "QUEUED":
        return False
    raw = (task_row or {}).get("enqueued_at")
    if not raw:
        return True
    try:
        enqueued_at = _parse_catalyst_datetime(raw)
    except (TypeError, ValueError):
        return True
    now = now or datetime.now(timezone.utc)
    return (now - enqueued_at).total_seconds() > QUEUED_STARTUP_GRACE_SECONDS


def running_is_stale(task_row, now=None):
    if str((task_row or {}).get("status") or "") != "RUNNING":
        return False
    raw = (task_row or {}).get("lease_expires_at")
    if not raw:
        return True
    try:
        expires = _parse_catalyst_datetime(raw)
    except (TypeError, ValueError):
        return True
    now = now or datetime.now(timezone.utc)
    return expires <= now


def _worker_target(scan_row):
    if scan_crm_provider(scan_row) == "salesforce":
        return (
            os.environ.get("SALESFORCE_WORKER_JOB_POOL_NAME", ""),
            os.environ.get("SALESFORCE_WORKER_FUNCTION_NAME", ""),
            "SALESFORCE_WORKER_NOT_CONFIGURED",
        )
    return (
        os.environ.get("ANALYTICS_WORKER_JOB_POOL_NAME", ""),
        os.environ.get("ANALYTICS_WORKER_FUNCTION_NAME", ""),
        "ANALYTICS_WORKER_NOT_CONFIGURED",
    )


def _download_path(scan_id, export_id):
    return f"/api/scans/{scan_id}/fix-export/{export_id}/file"


def _export_response(scan_id, task_row, status, **extra):
    request = extra.pop("request", None)
    payload = {
        "scanId": scan_id,
        "exportId": str(task_row.get("task_id") or ""),
        "taskStatus": str(task_row.get("status") or ""),
        "taskType": EXPORT_TASK_TYPE,
        "downloadPath": _download_path(scan_id, str(task_row.get("task_id") or "")),
    }
    if request:
        payload["filters"] = {
            "module": request.get("module") or "",
            "q": request.get("q") or "",
            "owners": list(request.get("owners") or []),
            "severity": request.get("severity") or "",
            "issueType": request.get("issueType") or "",
        }
    payload.update(extra)
    return json_response(payload, status)


def find_export_task(zcql, task_key):
    safe_key = _sql_string(task_key)
    results = zcql.execute_query(
        f"select * from pipeline_tasks where task_key = '{safe_key}' limit 1"
    )
    if not results:
        return None
    return results[0]["pipeline_tasks"]


def _submit_export_job(app, scan_row, task_id):
    pool_name, function_name, missing_code = _worker_target(scan_row)
    if not pool_name or not function_name:
        raise RuntimeError(missing_code)
    prefix = "sf" if scan_crm_provider(scan_row) == "salesforce" else "fx"
    job_name = f"{prefix}_{canonical_hash(f'{task_id}:{time.time_ns()}')[:16]}"
    job_payload = {
        "job_name": job_name,
        "jobpool_name": pool_name,
        "target_type": "Function",
        "target_name": function_name,
        "params": {"taskId": task_id},
    }
    job_response = app.job_scheduling().job.submit_job(job_payload)
    return job_response, pool_name, function_name, missing_code


def _queue_export(app, datastore, scan_row, task_row):
    pool_name, function_name, missing_code = _worker_target(scan_row)
    if not pool_name or not function_name:
        return {"ok": False, "code": missing_code, "task": task_row}

    task_table = datastore.table("pipeline_tasks")
    task_table.update_row(
        {
            "ROWID": task_row["ROWID"],
            "status": "QUEUED",
            "enqueued_at": catalyst_datetime_now(),
            "controlled_error_code": "",
        }
    )
    try:
        job_response, pool_name, function_name, missing_code = _submit_export_job(
            app, scan_row, task_row["task_id"]
        )
        catalyst_job_id = job_identifier(job_response)
    except RuntimeError as exc:
        code = str(exc)
        task_table.update_row(
            {
                "ROWID": task_row["ROWID"],
                "status": "PAUSED_RETRYABLE",
                "controlled_error_code": code[:100],
            }
        )
        return {"ok": False, "code": code, "task": task_row}
    except Exception as exc:  # noqa: BLE001 - submission outcome may be ambiguous
        catalyst_error = catalyst_error_details(exc)
        LOGGER.exception(
            "EXPORT_FIX_XLSX enqueue failed task_id=%s scan_id=%s",
            task_row.get("task_id"),
            scan_row.get("scan_id"),
        )
        try:
            status_code = int(catalyst_error.get("status_code") or 0)
        except (TypeError, ValueError):
            status_code = 0
        if 400 <= status_code < 500:
            task_table.update_row(
                {
                    "ROWID": task_row["ROWID"],
                    "status": "PAUSED_RETRYABLE",
                    "controlled_error_code": "WORKER_ENQUEUE_REJECTED",
                }
            )
            return {
                "ok": False,
                "code": "WORKER_ENQUEUE_REJECTED",
                "task": task_row,
            }
        task_table.update_row(
            {
                "ROWID": task_row["ROWID"],
                "status": "OUTCOME_UNKNOWN",
                "controlled_error_code": "WORKER_ENQUEUE_OUTCOME_UNKNOWN",
            }
        )
        return {
            "ok": False,
            "code": "WORKER_ENQUEUE_OUTCOME_UNKNOWN",
            "task": task_row,
        }

    if catalyst_job_id:
        try:
            task_table.update_row(
                {
                    "ROWID": task_row["ROWID"],
                    "catalyst_job_id": catalyst_job_id,
                }
            )
        except Exception:
            LOGGER.exception(
                "Could not persist EXPORT_FIX_XLSX job id task_id=%s",
                task_row.get("task_id"),
            )
    return {
        "ok": True,
        "task": {
            **task_row,
            "status": "QUEUED",
            "catalyst_job_id": catalyst_job_id,
        },
        "jobPoolName": pool_name,
        "functionName": function_name,
    }


def enqueue_fix_export(request, datastore, scan_id):
    """Create or reuse EXPORT_FIX_XLSX for the current Fix filters."""
    try:
        import zcatalyst_sdk

        app = zcatalyst_sdk.initialize()
        zcql = app.zcql()
        scan_row = find_owned_scan(zcql, scan_id, get_current_user_id(request))
        if not scan_row:
            return _error("SCAN_NOT_FOUND", "Scan was not found", 404)

        payload = request.get_json(silent=True)
        export_request = normalize_fix_export_request(payload)
        if not export_request["module"]:
            return _error("MODULE_REQUIRED", "module is required", 400)

        result_rows = find_analytics_results(zcql, scan_row["ROWID"])
        if _module_kpis(result_rows, export_request["module"]) is None:
            return _error(
                "FIX_INDEX_UNAVAILABLE",
                "Re-run the scan to use Fix",
                409,
            )

        task_key = fix_export_task_key(scan_id, export_request)
        task_row = find_export_task(zcql, task_key)
        if task_row:
            status = str(task_row.get("status") or "")
            result_file_key = str(task_row.get("result_file_key") or "").strip()
            if status == "SUCCEEDED" and result_file_key:
                return _export_response(
                    scan_id,
                    task_row,
                    200,
                    request=export_request,
                    alreadyExported=True,
                    alreadyQueued=False,
                )
            if status == "OUTCOME_UNKNOWN":
                return _error(
                    "WORKER_ENQUEUE_OUTCOME_UNKNOWN",
                    "The previous export job outcome is unknown",
                    409,
                )
            if status in ACTIVE_EXPORT_STATES:
                stale = queued_is_stale(task_row) or running_is_stale(task_row)
                if not stale:
                    return _export_response(
                        scan_id,
                        task_row,
                        202,
                        request=export_request,
                        alreadyExported=False,
                        alreadyQueued=True,
                    )
            elif status not in RESTARTABLE_EXPORT_STATES and not (
                status == "SUCCEEDED" and not result_file_key
            ):
                return _error(
                    "PIPELINE_TASK_STATE_CONFLICT",
                    "Fix export cannot run from the current task state",
                    409,
                )
        else:
            task_row = datastore.table("pipeline_tasks").insert_row(
                {
                    "task_id": f"task_{uuid.uuid4().hex}",
                    "task_key": task_key,
                    "scan_row_id": scan_row["ROWID"],
                    "task_type": EXPORT_TASK_TYPE,
                    "status": "PLANNED",
                    "attempt_count": 0,
                    "request_json": json.dumps(
                        export_request, separators=(",", ":"), sort_keys=True
                    ),
                }
            )

        queued = _queue_export(app, datastore, scan_row, task_row)
        if not queued.get("ok"):
            code = queued.get("code") or "WORKER_ENQUEUE_FAILED"
            status = 503 if code.endswith("NOT_CONFIGURED") else 409
            return _error(code, "Fix export could not be queued", status)
        return _export_response(
            scan_id,
            queued["task"],
            202,
            request=export_request,
            alreadyExported=False,
            alreadyQueued=False,
            jobPoolName=queued.get("jobPoolName"),
            functionName=queued.get("functionName"),
        )
    except AuthenticationRequired:
        raise
    except Exception as exc:  # noqa: BLE001 - return a controlled enqueue failure
        LOGGER.exception("Could not enqueue Fix export scan_id=%s: %s", scan_id, exc)
        return _error(
            "FIX_EXPORT_ENQUEUE_FAILED",
            "Fix export could not be queued",
            500,
        )
