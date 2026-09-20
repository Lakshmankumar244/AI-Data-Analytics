"""Salesforce Bulk API 2.0 Query result download and File Store CSV persist.

Independent of Zoho Bulk Read. Do not import bulk_read or zoho.client.
Do not call this during job polling; only after JobComplete / READY_TO_DOWNLOAD.

Endpoint:

    GET {instance_url}/services/data/v62.0/jobs/query/{provider_job_id}/results
    Accept: text/csv
    locator paging via Sforce-Locator (stop when missing or "null")

Existing bulk_read_jobs File Store columns (no new schema):

    source_file_id
    source_file_name
    source_file_size
    source_file_checksum
    downloaded_at
    downloaded_record_count

Salesforce job id is bulk_read_jobs.provider_job_id, never zoho_job_id.
The stored file is CSV, not a ZIP.
"""

import hashlib
import logging
import os
import tempfile
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests

from salesforce.bulk_query import SalesforceBulkError, salesforce_query_jobs_url

logger = logging.getLogger(__name__)

# Keep in sync with common.core.MAX_FILESTORE_UPLOAD_BYTES.
MAX_FILESTORE_UPLOAD_BYTES = 100 * 1024 * 1024
MAX_RESULT_PAGES = 10000
SALESFORCE_RESULT_MAX_RECORDS = 50000
READY_STATUSES = frozenset({"READY_TO_DOWNLOAD", "DOWNLOAD_RETRYABLE", "JobComplete"})
SFORCE_LOCATOR_HEADER = "Sforce-Locator"


def salesforce_query_results_url(instance_url, provider_job_id, locator=None):
    """Build the Query results URL. Locator is a query parameter, never path."""
    base = f"{salesforce_query_jobs_url(instance_url, provider_job_id)}/results"
    params = {"maxRecords": SALESFORCE_RESULT_MAX_RECORDS}
    if locator:
        params["locator"] = locator
    return f"{base}?{urlencode(params)}"


def next_salesforce_locator(headers) -> str:
    """Return the next locator, or None when Salesforce says there are no more pages."""
    if headers is None:
        return None
    raw = headers.get(SFORCE_LOCATOR_HEADER)
    if raw is None:
        raw = headers.get("sforce-locator")
    if raw is None:
        return None
    locator = str(raw).strip()
    if not locator or locator.lower() == "null":
        return None
    if any(ch.isspace() for ch in locator) or any(ord(ch) < 32 for ch in locator):
        raise SalesforceBulkError(
            "INVALID_LOCATOR", "Salesforce returned an invalid results locator"
        )
    return locator


def combine_salesforce_csv_pages(pages) -> bytes:
    """Keep the first CSV header; drop duplicate headers on later pages."""
    if not pages:
        return b""
    header = None
    rows = []
    for index, page in enumerate(pages):
        lines = _csv_lines(page)
        if not lines:
            if index == 0:
                continue
            raise SalesforceBulkError(
                "MALFORMED_CSV", "Salesforce CSV page is empty"
            )
        page_header = lines[0]
        if header is None:
            header = page_header
            rows.extend(lines[1:])
            continue
        if page_header != header:
            raise SalesforceBulkError(
                "MALFORMED_CSV", "Salesforce CSV page header does not match"
            )
        rows.extend(lines[1:])
    if header is None:
        return b""
    return ("\n".join([header, *rows]) + "\n").encode("utf-8")


def validate_salesforce_result_download(
    scan_row, bulk_row, connection_row, user_id=None
):
    """Reject the wrong provider, missing Salesforce job id, or unready jobs."""
    provider = str((scan_row or {}).get("crm_provider") or "").strip().lower()
    if provider != "salesforce":
        raise SalesforceBulkError(
            "WRONG_CRM_PROVIDER",
            "Salesforce Bulk results require a Salesforce scan",
        )
    if user_id is not None:
        owned_user = str((connection_row or {}).get("user_id") or "")
        if owned_user != str(user_id):
            raise SalesforceBulkError(
                "SCAN_NOT_OWNED", "Salesforce scan is not owned by this user"
            )
    scan_connection = str(
        _row_id((scan_row or {}).get("connection_row_id")) or ""
    )
    stored_connection = str(_row_id((connection_row or {}).get("ROWID")) or "")
    if not stored_connection or scan_connection != stored_connection:
        raise SalesforceBulkError(
            "SCAN_NOT_OWNED", "Salesforce scan is not owned by this user"
        )
    provider_job_id = str((bulk_row or {}).get("provider_job_id") or "").strip()
    if not provider_job_id:
        raise SalesforceBulkError(
            "PROVIDER_JOB_ID_MISSING",
            "The Salesforce Bulk job has no provider job identifier",
        )
    status = str((bulk_row or {}).get("status") or "").strip()
    already = status == "DOWNLOADED" and (bulk_row or {}).get("source_file_id")
    if already:
        return provider_job_id
    if status == "DOWNLOADING":
        raise SalesforceBulkError(
            "BULK_DOWNLOAD_RETRY_BLOCKED",
            "Salesforce result download is already in progress or must be inspected",
        )
    if status == "DOWNLOAD_UNKNOWN" and (bulk_row or {}).get("source_file_id"):
        raise SalesforceBulkError(
            "BULK_DOWNLOAD_RETRY_BLOCKED",
            "Salesforce result download is already in progress or must be inspected",
        )
    if status not in READY_STATUSES and not (
        status == "DOWNLOAD_UNKNOWN" and not (bulk_row or {}).get("source_file_id")
    ):
        raise SalesforceBulkError(
            "BULK_JOB_STATE_CONFLICT",
            "Salesforce Bulk result cannot be downloaded from this state",
        )
    return provider_job_id


def fetch_salesforce_query_result_pages(
    datastore, connection_row, provider_job_id
):
    """GET locator-paged CSV pages. Does not upload to File Store."""
    access_token, instance_url = _stored_access_token(datastore, connection_row)
    pages = []
    locator = None
    total_size = 0
    for _ in range(MAX_RESULT_PAGES):
        url = salesforce_query_results_url(instance_url, provider_job_id, locator)
        page_bytes, headers = _get_csv_page(url, access_token)
        total_size += len(page_bytes)
        if total_size > MAX_FILESTORE_UPLOAD_BYTES:
            raise SalesforceBulkError(
                "BULK_EXPORT_TOO_LARGE",
                "The CSV exceeds Catalyst File Store's 100 MB limit",
            )
        pages.append(page_bytes)
        locator = next_salesforce_locator(headers)
        if not locator:
            return pages, access_token, instance_url
    raise SalesforceBulkError(
        "INVALID_LOCATOR", "Salesforce result paging did not terminate"
    )


def persist_salesforce_csv_artifact(
    datastore, bulk_row, csv_bytes, folder, file_name
):
    """Upload CSV to File Store and write existing artifact columns.

    Catalyst File Store requires io.BufferedReader (open(..., "rb")), the same
    object Zoho passes. A bytes-like custom reader raises CatalystFilestoreError.
    """
    if not isinstance(csv_bytes, (bytes, bytearray)):
        raise SalesforceBulkError("MALFORMED_CSV", "Salesforce CSV is invalid")
    if len(csv_bytes) > MAX_FILESTORE_UPLOAD_BYTES:
        raise SalesforceBulkError(
            "BULK_EXPORT_TOO_LARGE",
            "The CSV exceeds Catalyst File Store's 100 MB limit",
        )
    checksum = hashlib.sha256(csv_bytes).hexdigest()
    record_count = _data_row_count(csv_bytes)
    disk_name = os.path.basename(str(file_name or "")) or "export.csv"
    try:
        with tempfile.TemporaryDirectory(prefix="sf_bulk_") as temp_dir:
            temp_path = os.path.join(temp_dir, disk_name)
            with open(temp_path, "wb") as temp_file:
                temp_file.write(csv_bytes)
            with open(temp_path, "rb") as source_file:
                uploaded = folder.upload_file(file_name, source_file)
        source_file_id = str((uploaded or {}).get("id") or "").strip()
        if not source_file_id:
            raise SalesforceBulkError(
                "FILESTORE_UPLOAD_FAILED",
                "File Store did not return a file identifier",
            )
    except SalesforceBulkError:
        raise
    except Exception as exc:
        logger.warning(
            "Salesforce File Store upload failed: %s",
            getattr(exc, "code", None) or type(exc).__name__,
        )
        raise SalesforceBulkError(
            "FILESTORE_UPLOAD_FAILED", "The CSV could not be stored"
        ) from exc

    artifact = {
        "source_file_id": source_file_id,
        "source_file_name": file_name,
        "source_file_size": len(csv_bytes),
        "source_file_checksum": checksum,
        "downloaded_record_count": record_count,
        "downloaded_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "status": "DOWNLOADED",
    }
    if bulk_row and bulk_row.get("ROWID"):
        update = {"ROWID": bulk_row["ROWID"], **artifact}
        datastore.table("bulk_read_jobs").update_row(update)
    return artifact


def download_salesforce_query_results(
    datastore,
    connection_row,
    scan_row,
    bulk_row,
    user_id=None,
    folder=None,
    module_row=None,
):
    """Download JobComplete CSV pages, combine them, and persist to File Store."""
    provider_job_id = validate_salesforce_result_download(
        scan_row, bulk_row, connection_row, user_id=user_id
    )
    if (
        str((bulk_row or {}).get("status") or "") == "DOWNLOADED"
        and (bulk_row or {}).get("source_file_id")
    ):
        return {
            "alreadyDownloaded": True,
            "status": "DOWNLOADED",
            "providerJobId": provider_job_id,
            "sourceFileId": str(bulk_row.get("source_file_id")),
            "sourceFileName": bulk_row.get("source_file_name"),
            "sourceFileSize": int(bulk_row.get("source_file_size") or 0),
            "sourceFileChecksum": bulk_row.get("source_file_checksum"),
            "downloadedRecordCount": int(bulk_row.get("downloaded_record_count") or 0),
        }

    bulk_table = datastore.table("bulk_read_jobs")
    try:
        download_attempt_count = int((bulk_row or {}).get("download_attempt_count") or 0) + 1
        bulk_table.update_row(
            {
                "ROWID": bulk_row["ROWID"],
                "status": "DOWNLOADING",
                "download_attempt_count": download_attempt_count,
                "controlled_error_code": "",
            }
        )
        bulk_row["status"] = "DOWNLOADING"
        bulk_row["download_attempt_count"] = download_attempt_count
    except Exception as exc:
        logger.warning("Could not lock Salesforce result download: %s", type(exc).__name__)
        raise SalesforceBulkError(
            "BULK_DOWNLOAD_LOCK_FAILED",
            "Salesforce result download was not started",
        ) from exc

    try:
        pages, _access_token, instance_url = fetch_salesforce_query_result_pages(
            datastore, connection_row, provider_job_id
        )
        del instance_url
        csv_bytes = combine_salesforce_csv_pages(pages)
        local_job_id = str((bulk_row or {}).get("bulk_job_id") or "bulk")
        file_name = f"{local_job_id}_{provider_job_id}.csv"
        upload_folder = folder if folder is not None else _default_filestore_folder()
        artifact = persist_salesforce_csv_artifact(
            datastore, bulk_row, csv_bytes, upload_folder, file_name
        )
    except SalesforceBulkError as exc:
        retry_status = (
            "DOWNLOAD_UNKNOWN"
            if exc.code == "FILESTORE_UPLOAD_FAILED"
            else "DOWNLOAD_RETRYABLE"
        )
        if exc.code == "BULK_EXPORT_TOO_LARGE":
            retry_status = "FAILED_TERMINAL"
        try:
            bulk_table.update_row(
                {
                    "ROWID": bulk_row["ROWID"],
                    "status": retry_status,
                    "controlled_error_code": str(exc.code or "")[:100],
                }
            )
        except Exception:
            logger.warning(
                "Could not persist Salesforce download failure bulkRowId=%s",
                bulk_row.get("ROWID"),
            )
        raise

    if module_row and module_row.get("ROWID"):
        datastore.table("scan_module_runs").update_row(
            {
                "ROWID": module_row["ROWID"],
                "status": "DOWNLOADED",
                "records_downloaded": artifact["downloaded_record_count"],
            }
        )
    return {
        "alreadyDownloaded": False,
        "status": "DOWNLOADED",
        "providerJobId": provider_job_id,
        "sourceFileId": artifact["source_file_id"],
        "sourceFileName": artifact["source_file_name"],
        "sourceFileSize": artifact["source_file_size"],
        "sourceFileChecksum": artifact["source_file_checksum"],
        "downloadedRecordCount": artifact["downloaded_record_count"],
        "pageCount": len(pages),
    }


def _default_filestore_folder():
    folder_id = str(os.environ.get("BULK_EXPORT_FOLDER_ID") or "").strip()
    if not folder_id.isdigit():
        raise SalesforceBulkError(
            "BULK_EXPORT_FOLDER_NOT_CONFIGURED",
            "The Bulk export folder is not configured",
        )
    import zcatalyst_sdk

    return zcatalyst_sdk.initialize().filestore().folder(int(folder_id))


def _stored_access_token(datastore, connection_row):
    from salesforce.client import get_salesforce_access_token

    try:
        return get_salesforce_access_token(datastore, connection_row)
    except Exception as exc:
        code = getattr(exc, "code", None)
        if code:
            raise SalesforceBulkError(code, str(exc)) from exc
        logger.warning("Salesforce token refresh failed: %s", type(exc).__name__)
        raise SalesforceBulkError(
            "TOKEN_REFRESH_FAILED", "Salesforce token refresh failed"
        ) from exc


def _get_csv_page(url, access_token):
    try:
        response = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "text/csv",
            },
            timeout=(15, 120),
        )
    except requests.RequestException as exc:
        logger.warning(
            "Salesforce bulk results request failed: %s", type(exc).__name__
        )
        raise SalesforceBulkError(
            "SALESFORCE_BULK_RESULTS_FAILED",
            "Salesforce Bulk results request failed",
        ) from exc

    if not response.ok:
        error_code = _error_code_from_body(response)
        logger.warning(
            "Salesforce bulk results request failed: status=%s errorCode=%s",
            response.status_code,
            error_code or "",
        )
        raise SalesforceBulkError(*_map_results_http_error(response.status_code, error_code))

    content_type = str(response.headers.get("Content-Type") or "").lower()
    if "json" in content_type:
        raise SalesforceBulkError(
            "MALFORMED_CSV", "Salesforce did not return CSV results"
        )
    return response.content or b"", response.headers


def _error_code_from_body(response):
    try:
        payload = response.json()
    except ValueError:
        return None
    if isinstance(payload, list) and payload:
        first = payload[0] if isinstance(payload[0], dict) else {}
        return str(first.get("errorCode") or first.get("error") or "").strip() or None
    if isinstance(payload, dict):
        return (
            str(payload.get("errorCode") or payload.get("error") or "").strip() or None
        )
    return None


def _map_results_http_error(status, error_code):
    if status in {401, 403}:
        return "TOKEN_REFRESH_FAILED", "Salesforce token refresh failed"
    if status == 404 or error_code in {"NOT_FOUND", "INVALID_JOB"}:
        return "PROVIDER_JOB_NOT_FOUND", "Salesforce Bulk job was not found"
    if error_code:
        return "SALESFORCE_BULK_RESULTS_FAILED", "Salesforce rejected the Bulk results request"
    if 400 <= status < 500:
        return "SALESFORCE_BULK_RESULTS_FAILED", "Salesforce rejected the Bulk results request"
    return "SALESFORCE_BULK_RESULTS_FAILED", "Salesforce Bulk results request failed"


def _csv_lines(page):
    if page is None:
        raise SalesforceBulkError("MALFORMED_CSV", "Salesforce CSV is invalid")
    if isinstance(page, bytes):
        try:
            text = page.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise SalesforceBulkError(
                "MALFORMED_CSV", "Salesforce CSV is invalid"
            ) from exc
    else:
        text = str(page)
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _data_row_count(csv_bytes: bytes) -> int:
    lines = _csv_lines(csv_bytes)
    if not lines:
        return 0
    return max(0, len(lines) - 1)


def _row_id(value):
    if isinstance(value, dict):
        return value.get("ROWID") or value.get("rowid")
    return value
