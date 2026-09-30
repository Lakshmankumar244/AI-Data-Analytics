"""Owned Fix XLSX status and private backend download."""

import logging
import re

from flask import make_response

from analytics.repository import find_owned_scan
from common.core import AuthenticationRequired, get_current_user_id, json_response
from pipeline.fix_export_enqueue import EXPORT_TASK_TYPE
from storage.extract_store import ExtractStorageError, get_extract
from storage.locator import stratus_object_key


LOGGER = logging.getLogger(__name__)
XLSX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def _error(code, message, status):
    return json_response({"error": {"code": code, "message": message}}, status)


def _sql_string(value):
    return str(value or "").replace("'", "''")


def _download_path(scan_id, export_id):
    return f"/api/scans/{scan_id}/fix-export/{export_id}/file"


def _filename(module, export_id):
    module_part = re.sub(r"[^A-Za-z0-9._-]+", "_", str(module or ""))[:40] or "module"
    export_part = re.sub(r"[^A-Za-z0-9._-]+", "_", str(export_id or ""))[:40] or "export"
    return f"fix-{module_part}-{export_part}.xlsx"


def _bytes_body(payload):
    if payload is None:
        return b""
    if isinstance(payload, (bytes, bytearray)):
        return bytes(payload)
    if hasattr(payload, "read") and not isinstance(payload, str):
        data = payload.read()
        if isinstance(data, (bytes, bytearray)):
            return bytes(data)
        return str(data).encode("utf-8")
    if isinstance(payload, str):
        return payload.encode("utf-8")
    return bytes(payload)


def find_owned_export_task(zcql, scan_row, export_id):
    safe_id = _sql_string(str(export_id or "").strip())
    if not safe_id:
        return None
    results = zcql.execute_query(
        "select * from pipeline_tasks where "
        f"task_id = '{safe_id}' and "
        f"scan_row_id = {int(scan_row['ROWID'])} and "
        f"task_type = '{EXPORT_TASK_TYPE}' limit 1"
    )
    if not results:
        return None
    return results[0]["pipeline_tasks"]


def get_fix_export(request, datastore, scan_id, export_id):
    """Return export task status for the owning tenant. Never streams the file."""
    del datastore
    try:
        import zcatalyst_sdk

        zcql = zcatalyst_sdk.initialize().zcql()
        scan_row = find_owned_scan(zcql, scan_id, get_current_user_id(request))
        if not scan_row:
            return _error("SCAN_NOT_FOUND", "Scan was not found", 404)
        task_row = find_owned_export_task(zcql, scan_row, export_id)
        if not task_row:
            return _error("EXPORT_NOT_FOUND", "Fix export was not found", 404)
        status = str(task_row.get("status") or "")
        return json_response(
            {
                "scanId": scan_id,
                "exportId": str(task_row.get("task_id") or export_id),
                "taskStatus": status,
                "taskType": EXPORT_TASK_TYPE,
                "ready": status == "SUCCEEDED" and bool(str(task_row.get("result_file_key") or "").strip()),
                "downloadPath": _download_path(scan_id, str(task_row.get("task_id") or export_id)),
            }
        )
    except AuthenticationRequired:
        raise
    except Exception as exc:  # noqa: BLE001 - return a controlled read failure
        LOGGER.exception(
            "Could not read Fix export scan_id=%s export_id=%s: %s",
            scan_id,
            export_id,
            exc,
        )
        return _error("FIX_EXPORT_READ_FAILED", "Fix export could not be read", 500)


def download_fix_export(request, datastore, scan_id, export_id):
    """Stream the private XLSX through the HTTP function. No Stratus URL."""
    del datastore
    try:
        import zcatalyst_sdk

        app = zcatalyst_sdk.initialize()
        zcql = app.zcql()
        scan_row = find_owned_scan(zcql, scan_id, get_current_user_id(request))
        if not scan_row:
            return _error("SCAN_NOT_FOUND", "Scan was not found", 404)
        task_row = find_owned_export_task(zcql, scan_row, export_id)
        if not task_row:
            return _error("EXPORT_NOT_FOUND", "Fix export was not found", 404)
        if str(task_row.get("status") or "") != "SUCCEEDED":
            return _error("EXPORT_NOT_READY", "Fix export is not ready", 409)
        object_key = stratus_object_key(task_row.get("result_file_key"))
        if not object_key:
            return _error("EXPORT_NOT_READY", "Fix export is not ready", 409)
        body = _bytes_body(get_extract(object_key, app=app))
        module = ""
        raw_request = task_row.get("request_json")
        if isinstance(raw_request, dict):
            module = str(raw_request.get("module") or "")
        elif raw_request:
            try:
                import json

                parsed = json.loads(raw_request)
                if isinstance(parsed, dict):
                    module = str(parsed.get("module") or "")
            except (TypeError, ValueError, json.JSONDecodeError):
                module = ""
        filename = _filename(module, task_row.get("task_id") or export_id)
        response = make_response(body)
        response.headers["Content-Type"] = XLSX_CONTENT_TYPE
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
    except ExtractStorageError as exc:
        if exc.code == "EXTRACT_NOT_FOUND":
            return _error("EXPORT_NOT_FOUND", "Fix export was not found", 404)
        LOGGER.exception(
            "Could not download Fix export scan_id=%s export_id=%s",
            scan_id,
            export_id,
        )
        return _error("FIX_EXPORT_READ_FAILED", "Fix export could not be read", 500)
    except AuthenticationRequired:
        raise
    except Exception as exc:  # noqa: BLE001 - return a controlled download failure
        LOGGER.exception(
            "Could not download Fix export scan_id=%s export_id=%s: %s",
            scan_id,
            export_id,
            exc,
        )
        return _error("FIX_EXPORT_READ_FAILED", "Fix export could not be read", 500)
