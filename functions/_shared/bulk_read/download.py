"""Download a completed Bulk Read ZIP and store it in Catalyst File Store."""

import hashlib
import json
import logging
import os
import tempfile
import uuid
import zipfile
from datetime import datetime, timedelta, timezone

import requests
import zcatalyst_sdk
from flask import Request

from common.core import (
    API_VERSION,
    DiscoveryError,
    MAX_BULK_UNCOMPRESSED_BYTES,
    MAX_FILESTORE_UPLOAD_BYTES,
    canonical_hash,
    foreign_row_id,
    from_catalyst_datetime,
    get_current_user_id,
    json_response,
    to_catalyst_column_datetime,
    to_zoho_datetime,
)
from connections.access import resolve_action_connection
from connections.token import get_connection_access_token
from common.profiler import profile_stage

logger = logging.getLogger(__name__)

def download_bulk_read_result(
    request: Request, datastore, scan_id: str, bulk_job_id: str, connection_row=None
):
    """Download one completed Zoho result and persist its ZIP in File Store."""
    zcql = zcatalyst_sdk.initialize().zcql()
    safe_scan_id = scan_id.replace("'", "''")
    scan_results = zcql.execute_query(
        f"select * from scan_jobs where scan_id = '{safe_scan_id}' limit 1"
    )
    if not scan_results:
        return json_response(
            {"error": {"code": "SCAN_NOT_FOUND", "message": "Scan was not found"}}, 404
        )
    scan_row = scan_results[0]["scan_jobs"]

    connection_row = resolve_action_connection(
        zcql, scan_row, request=request, connection_row=connection_row
    )
    if not connection_row:
        return json_response(
            {"error": {"code": "ZOHO_CONNECTION_REQUIRED", "message": "Reconnect Zoho CRM"}},
            409,
        )
    safe_bulk_job_id = bulk_job_id.replace("'", "''")
    bulk_results = zcql.execute_query(
        "select * from bulk_read_jobs where "
        f"bulk_job_id = '{safe_bulk_job_id}' limit 1"
    )
    if not bulk_results:
        return json_response(
            {
                "error": {
                    "code": "BULK_JOB_NOT_FOUND",
                    "message": "Bulk Read job was not found",
                }
            },
            404,
        )
    bulk_row = bulk_results[0]["bulk_read_jobs"]

    module_row_id = str(foreign_row_id(bulk_row.get("scan_module_row_id")))
    if not module_row_id.isdigit():
        return json_response(
            {
                "error": {
                    "code": "INVALID_BULK_JOB_LINK",
                    "message": "Bulk Read job has an invalid module link",
                }
            },
            500,
        )
    module_results = zcql.execute_query(
        f"select * from scan_module_runs where ROWID = {module_row_id} limit 1"
    )
    if not module_results:
        return json_response(
            {
                "error": {
                    "code": "BULK_JOB_NOT_FOUND",
                    "message": "Bulk Read job was not found",
                }
            },
            404,
        )
    module_row = module_results[0]["scan_module_runs"]
    if str(foreign_row_id(module_row.get("scan_row_id"))) != str(scan_row["ROWID"]):
        return json_response(
            {
                "error": {
                    "code": "BULK_JOB_NOT_FOUND",
                    "message": "Bulk Read job was not found",
                }
            },
            404,
        )

    bulk_status = bulk_row.get("status")
    if bulk_status == "DOWNLOADED" and bulk_row.get("source_file_id"):
        return json_response(
            {
                "scanId": scan_id,
                "bulkJobId": bulk_job_id,
                "module": module_row["module_api_name"],
                "status": "DOWNLOADED",
                "sourceFileId": bulk_row["source_file_id"],
                "sourceFileName": bulk_row.get("source_file_name"),
                "sourceFileSize": int(bulk_row.get("source_file_size") or 0),
                "sourceFileChecksum": bulk_row.get("source_file_checksum"),
                "alreadyDownloaded": True,
                "crmApiCalls": 0,
                "creditsConsumed": 0,
            }
        )
    if bulk_status in {"DOWNLOADING", "DOWNLOAD_UNKNOWN"}:
        return json_response(
            {
                "error": {
                    "code": "BULK_DOWNLOAD_RETRY_BLOCKED",
                    "message": (
                        f"Job is {bulk_status}; retry is blocked until its File Store "
                        "outcome is inspected"
                    ),
                }
            },
            409,
        )
    if bulk_status not in {"READY_TO_DOWNLOAD", "DOWNLOAD_RETRYABLE"}:
        return json_response(
            {
                "error": {
                    "code": "BULK_JOB_STATE_CONFLICT",
                    "message": f"Bulk Read result cannot be downloaded from state {bulk_status}",
                }
            },
            409,
        )

    zoho_job_id = bulk_row.get("zoho_job_id")
    if not zoho_job_id:
        return json_response(
            {
                "error": {
                    "code": "ZOHO_JOB_ID_MISSING",
                    "message": "The completed Bulk Read job has no Zoho job identifier",
                }
            },
            409,
        )
    folder_id_value = os.environ.get("BULK_EXPORT_FOLDER_ID", "")
    if not folder_id_value.isdigit():
        return json_response(
            {
                "error": {
                    "code": "BULK_EXPORT_FOLDER_NOT_CONFIGURED",
                    "message": "The Bulk Read export folder is not configured",
                }
            },
            500,
        )

    try:
        access_token, api_domain, token_refreshed = get_connection_access_token(
            datastore, connection_row
        )
    except DiscoveryError as exc:
        return json_response(
            {"error": {"code": exc.code, "message": str(exc)}}, 502
        )

    bulk_table = datastore.table("bulk_read_jobs")
    module_table = datastore.table("scan_module_runs")
    try:
        download_attempt_count = int(bulk_row.get("download_attempt_count") or 0) + 1
        bulk_table.update_row(
            {
                "ROWID": bulk_row["ROWID"],
                "status": "DOWNLOADING",
                "download_attempt_count": download_attempt_count,
                "controlled_error_code": "",
            }
        )
    except Exception as exc:  # noqa: BLE001 - provider call has not happened yet
        logger.exception("Could not lock Bulk Read download %s: %s", bulk_job_id, exc)
        return json_response(
            {
                "error": {
                    "code": "BULK_DOWNLOAD_LOCK_FAILED",
                    "message": "Bulk Read result download was not started",
                }
            },
            500,
        )

    file_name = f"{bulk_job_id}_{zoho_job_id}.zip"
    try:
        with tempfile.TemporaryDirectory(prefix="crm_bulk_") as temp_dir:
            temp_path = os.path.join(temp_dir, file_name)
            try:
                with profile_stage(
                    "extraction",
                    "zoho_result_download",
                    scanId=scan_id,
                    bulkJobId=bulk_job_id,
                ):
                    provider_response = requests.get(
                        f"{api_domain}/crm/bulk/{API_VERSION}/read/{zoho_job_id}/result",
                        headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
                        stream=True,
                        timeout=(15, 120),
                    )
                    provider_response.raise_for_status()
            except requests.RequestException as exc:
                logger.exception("Zoho result download failed for %s: %s", bulk_job_id, exc)
                bulk_table.update_row(
                    {
                        "ROWID": bulk_row["ROWID"],
                        "status": "DOWNLOAD_RETRYABLE",
                        "controlled_error_code": "ZOHO_RESULT_DOWNLOAD_FAILED",
                    }
                )
                return json_response(
                    {
                        "error": {
                            "code": "ZOHO_RESULT_DOWNLOAD_FAILED",
                            "message": "Zoho did not return the Bulk Read result file",
                        },
                        "crmApiCallsAttempted": 1,
                        "creditsPossiblyConsumed": 1,
                    },
                    502,
                )

            content_length = provider_response.headers.get("Content-Length")
            try:
                declared_size = int(content_length) if content_length else None
            except (TypeError, ValueError):
                declared_size = None
            if declared_size is not None and declared_size > MAX_FILESTORE_UPLOAD_BYTES:
                bulk_table.update_row(
                    {
                        "ROWID": bulk_row["ROWID"],
                        "status": "FAILED_TERMINAL",
                        "controlled_error_code": "BULK_EXPORT_TOO_LARGE",
                    }
                )
                return json_response(
                    {
                        "error": {
                            "code": "BULK_EXPORT_TOO_LARGE",
                            "message": "The ZIP exceeds Catalyst File Store's 100 MB limit",
                        },
                        "crmApiCalls": 1,
                        "creditsConsumed": 1,
                    },
                    413,
                )

            source_hash = hashlib.sha256()
            source_size = 0
            with profile_stage(
                "extraction",
                "zoho_result_stream",
                scanId=scan_id,
                bulkJobId=bulk_job_id,
            ):
                with open(temp_path, "wb") as temp_file:
                    for chunk in provider_response.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        source_size += len(chunk)
                        if source_size > MAX_FILESTORE_UPLOAD_BYTES:
                            raise ValueError("BULK_EXPORT_TOO_LARGE")
                        source_hash.update(chunk)
                        temp_file.write(chunk)

            if not zipfile.is_zipfile(temp_path):
                raise ValueError("BULK_EXPORT_INVALID_ZIP")
            with zipfile.ZipFile(temp_path, "r") as archive:
                members = [entry for entry in archive.infolist() if not entry.is_dir()]
                csv_members = [
                    entry for entry in members if entry.filename.lower().endswith(".csv")
                ]
                if len(csv_members) != 1:
                    raise ValueError("BULK_EXPORT_INVALID_CONTENTS")
                if sum(entry.file_size for entry in members) > MAX_BULK_UNCOMPRESSED_BYTES:
                    raise ValueError("BULK_EXPORT_UNCOMPRESSED_TOO_LARGE")
                corrupt_member = archive.testzip()
                if corrupt_member:
                    raise ValueError("BULK_EXPORT_CORRUPT_ZIP")

            try:
                with profile_stage(
                    "extraction",
                    "filestore_upload",
                    scanId=scan_id,
                    bulkJobId=bulk_job_id,
                    sourceFileSize=source_size,
                ):
                    filestore = zcatalyst_sdk.initialize().filestore()
                    folder = filestore.folder(int(folder_id_value))
                    with open(temp_path, "rb") as source_file:
                        uploaded_file = folder.upload_file(file_name, source_file)
                    source_file_id = uploaded_file.get("id")
                    if not source_file_id:
                        raise ValueError("File Store did not return a file identifier")
            except Exception as exc:  # noqa: BLE001 - upload outcome can be ambiguous
                logger.exception("File Store upload failed for %s: %s", bulk_job_id, exc)
                bulk_table.update_row(
                    {
                        "ROWID": bulk_row["ROWID"],
                        "status": "DOWNLOAD_UNKNOWN",
                        "controlled_error_code": "FILESTORE_UPLOAD_OUTCOME_UNKNOWN",
                    }
                )
                return json_response(
                    {
                        "error": {
                            "code": "FILESTORE_UPLOAD_OUTCOME_UNKNOWN",
                            "message": "The File Store upload outcome must be inspected",
                        },
                        "crmApiCalls": 1,
                        "creditsConsumed": 1,
                    },
                    500,
                )

            source_checksum = source_hash.hexdigest()
            downloaded_at = to_catalyst_column_datetime(datetime.now(timezone.utc))
            try:
                bulk_table.update_row(
                    {
                        "ROWID": bulk_row["ROWID"],
                        "status": "DOWNLOADED",
                        "source_file_id": str(source_file_id),
                        "source_file_name": file_name,
                        "source_file_size": source_size,
                        "source_file_checksum": source_checksum,
                        "downloaded_at": downloaded_at,
                        "controlled_error_code": "",
                    }
                )
                module_table.update_row(
                    {"ROWID": module_row["ROWID"], "status": "DOWNLOADED"}
                )
            except Exception as exc:  # noqa: BLE001 - uploaded file already exists
                logger.exception(
                    "File %s uploaded but metadata persistence failed for %s: %s",
                    source_file_id,
                    bulk_job_id,
                    exc,
                )
                try:
                    bulk_table.update_row(
                        {
                            "ROWID": bulk_row["ROWID"],
                            "status": "DOWNLOAD_UNKNOWN",
                            "controlled_error_code": "FILESTORE_METADATA_PERSIST_FAILED",
                        }
                    )
                except Exception:  # noqa: BLE001 - original persistence error is primary
                    logger.exception("Could not mark download %s as unknown", bulk_job_id)
                return json_response(
                    {
                        "error": {
                            "code": "FILESTORE_METADATA_PERSIST_FAILED",
                            "message": "The ZIP was stored but its metadata could not be saved",
                        },
                        "sourceFileId": str(source_file_id),
                        "crmApiCalls": 1,
                        "creditsConsumed": 1,
                    },
                    500,
                )
    except ValueError as exc:
        error_code = str(exc)
        controlled_errors = {
            "BULK_EXPORT_TOO_LARGE": "The ZIP exceeds Catalyst File Store's 100 MB limit",
            "BULK_EXPORT_INVALID_ZIP": "Zoho returned a file that is not a ZIP archive",
            "BULK_EXPORT_INVALID_CONTENTS": "The ZIP does not contain exactly one CSV file",
            "BULK_EXPORT_UNCOMPRESSED_TOO_LARGE": "The uncompressed export is too large",
            "BULK_EXPORT_CORRUPT_ZIP": "The ZIP archive failed its integrity check",
        }
        if error_code not in controlled_errors:
            raise
        logger.error("Bulk export validation failed for %s: %s", bulk_job_id, error_code)
        bulk_table.update_row(
            {
                "ROWID": bulk_row["ROWID"],
                "status": "FAILED_TERMINAL",
                "controlled_error_code": error_code,
            }
        )
        return json_response(
            {
                "error": {"code": error_code, "message": controlled_errors[error_code]},
                "crmApiCalls": 1,
                "creditsConsumed": 1,
            },
            422,
        )

    return json_response(
        {
            "scanId": scan_id,
            "bulkJobId": bulk_job_id,
            "module": module_row["module_api_name"],
            "status": "DOWNLOADED",
            "sourceFileId": str(source_file_id),
            "sourceFileName": file_name,
            "sourceFileSize": source_size,
            "sourceFileChecksum": source_checksum,
            "alreadyDownloaded": False,
            "tokenRefreshed": token_refreshed,
            "crmApiCalls": 1,
            "creditsConsumed": 1,
        },
        201,
    )
