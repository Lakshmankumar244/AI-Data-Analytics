"""Private Stratus + legacy File Store access for CRM extraction artifacts.

Verified zcatalyst_sdk 1.4.0 Bucket APIs used here:

- put_object(key, body, options=None) — body is BufferedReader/str/bytes;
  do not pass extract_upload
- get_object(key) — returns the object bytes
- delete_path(path) — admin prefix delete

Do not generate public or presigned URLs for application reads.
"""

from __future__ import annotations

import hashlib
import os
import tempfile

from storage.locator import (
    BACKEND_FILESTORE,
    BACKEND_STRATUS,
    resolve_extract_locator,
    stratus_object_key,
)


CHUNK_SIZE = 1024 * 1024
SCAN_PREFIX = "exports"


class ExtractStorageError(Exception):
    """Storage adapter failure. `code` is used by existing download state machines."""

    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def bucket_name():
    return str(os.environ.get("STRATUS_BUCKET_NAME") or "").strip()


def require_bucket_name():
    name = bucket_name()
    if not name:
        raise ExtractStorageError(
            "STRATUS_BUCKET_NOT_CONFIGURED",
            "The Stratus extract bucket is not configured",
        )
    return name


def scan_extract_prefix(scan_id):
    scan = _safe_key_part(scan_id, "scan_id")
    return f"{SCAN_PREFIX}/{scan}/"


def build_object_key(scan_id, bulk_job_id, provider_job_id, extension):
    """Build exports/{scan_id}/{bulk_job_id}_{provider_job_id}.zip|csv."""
    scan = _safe_key_part(scan_id, "scan_id")
    bulk = _safe_key_part(bulk_job_id, "bulk_job_id")
    provider = _safe_key_part(provider_job_id, "provider_job_id")
    suffix = str(extension or "").strip().lstrip(".").lower()
    if suffix not in {"zip", "csv"}:
        raise ExtractStorageError(
            "EXTRACT_OBJECT_KEY_INVALID",
            "Extract object key extension must be zip or csv",
        )
    return f"{SCAN_PREFIX}/{scan}/{bulk}_{provider}.{suffix}"


def build_fix_object_key(scan_id, module_api_name, batch_number):
    """Build exports/{scan_id}/fix/{module}/batch-{n}.jsonl for defective-record sidecars."""
    scan = _safe_key_part(scan_id, "scan_id")
    module = _safe_key_part(module_api_name, "module_api_name")
    try:
        number = int(batch_number)
    except (TypeError, ValueError) as exc:
        raise ExtractStorageError(
            "EXTRACT_OBJECT_KEY_INVALID",
            "Fix sidecar batch number is invalid",
        ) from exc
    if number < 1:
        raise ExtractStorageError(
            "EXTRACT_OBJECT_KEY_INVALID",
            "Fix sidecar batch number is invalid",
        )
    return f"{SCAN_PREFIX}/{scan}/fix/{module}/batch-{number}.jsonl"


def build_fix_export_object_key(scan_id, export_id):
    """Build exports/{scan_id}/fix/exports/{export_id}.xlsx for Fix workbooks."""
    scan = _safe_key_part(scan_id, "scan_id")
    export = _safe_key_part(export_id, "export_id")
    return f"{SCAN_PREFIX}/{scan}/fix/exports/{export}.xlsx"


def put_extract(key, body, app=None):
    """Upload one extract object. Does not call File Store. No extract_upload."""
    object_key = stratus_object_key(key)
    if not object_key:
        raise ExtractStorageError(
            "EXTRACT_OBJECT_KEY_INVALID",
            "Extract object key is missing",
        )
    bucket = _bucket(app)
    try:
        result = bucket.put_object(object_key, body)
    except ExtractStorageError:
        raise
    except Exception as exc:
        raise ExtractStorageError(
            "FILESTORE_UPLOAD_FAILED",
            "The extract could not be stored",
        ) from exc
    if result is not True:
        raise ExtractStorageError(
            "FILESTORE_UPLOAD_FAILED",
            "Stratus did not confirm the extract upload",
        )
    return object_key


def get_extract(key, app=None):
    """Download one extract object as returned by Bucket.get_object (bytes)."""
    object_key = stratus_object_key(key)
    if not object_key:
        raise ExtractStorageError(
            "EXTRACT_OBJECT_KEY_INVALID",
            "Extract object key is missing",
        )
    try:
        return _bucket(app).get_object(object_key)
    except ExtractStorageError:
        raise
    except Exception as exc:
        if _is_missing_object(exc):
            raise ExtractStorageError(
                "EXTRACT_NOT_FOUND",
                "The extract object was not found",
            ) from exc
        raise ExtractStorageError(
            "EXTRACT_DOWNLOAD_FAILED",
            "The extract could not be downloaded",
        ) from exc


def delete_scan_extracts(scan_id, app=None):
    """Delete exports/{scan_id}/. Idempotent when the prefix is already absent.

    Does not delete legacy File Store objects.
    """
    prefix = scan_extract_prefix(scan_id)
    try:
        _bucket(app).delete_path(prefix)
    except ExtractStorageError:
        raise
    except Exception as exc:
        if _is_missing_object(exc):
            return prefix
        raise ExtractStorageError(
            "EXTRACT_DELETE_FAILED",
            "The scan extract prefix could not be deleted",
        ) from exc
    return prefix


def download_extract_to_tempfile(
    bulk_row,
    app=None,
    prefix="ada_bulk_",
    suffix=".zip",
    require_checksum=True,
):
    """Dual-read an extract into a temp file and optionally verify SHA-256."""
    locator = resolve_extract_locator(bulk_row)
    if locator is None:
        raise ValueError("Bulk Read source file identifier is invalid")

    temp_file = tempfile.NamedTemporaryFile(prefix=prefix, suffix=suffix, delete=False)
    temp_path = temp_file.name
    source_hash = hashlib.sha256()
    try:
        if locator.backend == BACKEND_STRATUS:
            payload = get_extract(locator.locator, app=app)
            with temp_file:
                _write_payload(payload, temp_file, source_hash)
        elif locator.backend == BACKEND_FILESTORE:
            folder_id = str(os.environ.get("BULK_EXPORT_FOLDER_ID") or "").strip()
            if not folder_id.isdigit():
                raise ValueError("BULK_EXPORT_FOLDER_ID is not configured")
            response = (
                _sdk_app(app)
                .filestore()
                .folder(int(folder_id))
                .get_file_stream(int(locator.locator))
            )
            with temp_file:
                _write_payload(response, temp_file, source_hash)
        else:
            raise ValueError("Bulk Read source file identifier is invalid")
        checksum = str((bulk_row or {}).get("source_file_checksum") or "").strip()
        digest = source_hash.hexdigest()
        if require_checksum:
            if not checksum or digest != checksum:
                raise ValueError("Downloaded File Store checksum does not match")
        elif checksum and digest != checksum:
            raise ValueError("Downloaded File Store checksum does not match")
        return temp_path
    except Exception:
        try:
            temp_file.close()
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        raise


def _sdk_app(app=None):
    if app is not None:
        return app
    import zcatalyst_sdk

    return zcatalyst_sdk.initialize()


def _bucket(app=None):
    name = require_bucket_name()
    stratus = getattr(_sdk_app(app), "stratus", None)
    if not callable(stratus):
        raise ExtractStorageError(
            "STRATUS_BUCKET_NOT_CONFIGURED",
            "The Stratus extract bucket is not configured",
        )
    return stratus().bucket(name)


def _safe_key_part(value, field_name):
    part = str(value or "").strip()
    if not part or "/" in part or "\\" in part or ".." in part:
        raise ExtractStorageError(
            "EXTRACT_OBJECT_KEY_INVALID",
            f"Extract object key {field_name} is invalid",
        )
    return part


def _write_payload(payload, dest, source_hash):
    if payload is None:
        raise ExtractStorageError(
            "EXTRACT_DOWNLOAD_FAILED",
            "The extract could not be downloaded",
        )
    if hasattr(payload, "iter_content"):
        for chunk in payload.iter_content(chunk_size=CHUNK_SIZE):
            if not chunk:
                continue
            source_hash.update(chunk)
            dest.write(chunk)
        return
    if hasattr(payload, "read") and not isinstance(payload, (bytes, bytearray)):
        while True:
            chunk = payload.read(CHUNK_SIZE)
            if not chunk:
                break
            source_hash.update(chunk)
            dest.write(chunk)
        return
    data = payload if isinstance(payload, (bytes, bytearray)) else bytes(payload)
    view = memoryview(data)
    for start in range(0, len(view), CHUNK_SIZE):
        chunk = view[start : start + CHUNK_SIZE].tobytes()
        source_hash.update(chunk)
        dest.write(chunk)


def _is_missing_object(exc):
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(exc, "http_status_code", None)
    if status == 404:
        return True
    code = str(getattr(exc, "code", "") or "").upper()
    if code in {"OBJECT_NOT_FOUND", "NO_SUCH_KEY", "NOT_FOUND", "NO_SUCH_OBJECT"}:
        return True
    message = str(exc).lower()
    return "not found" in message or "nosuchkey" in message or "no such key" in message
