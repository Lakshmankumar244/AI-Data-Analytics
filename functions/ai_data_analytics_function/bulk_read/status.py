"""Refresh and persist Zoho Bulk Read job status."""

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
from connections.repository import find_scan_connection
from connections.routes import get_connection_access_token

logger = logging.getLogger(__name__)

def refresh_bulk_read_status(
    request: Request, datastore, scan_id: str, bulk_job_id: str
):
    """Refresh one submitted Bulk Read job exactly once per invocation."""
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

    user_id = get_current_user_id(request)
    connection_row = find_scan_connection(zcql, user_id, scan_row)
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
    if bulk_status == "READY_TO_DOWNLOAD":
        next_page_token = bulk_row.get("next_page_token")
        return json_response(
            {
                "scanId": scan_id,
                "bulkJobId": bulk_job_id,
                "module": module_row["module_api_name"],
                "status": "READY_TO_DOWNLOAD",
                "providerState": "COMPLETED",
                "providerRecordCount": int(
                    bulk_row.get("provider_record_count") or 0
                ),
                "moreRecords": bool(next_page_token),
                "downloadAvailable": True,
                "cached": True,
                "crmApiCalls": 0,
                "creditsConsumed": 0,
            }
        )
    if bulk_status == "FAILED_TERMINAL":
        return json_response(
            {
                "scanId": scan_id,
                "bulkJobId": bulk_job_id,
                "module": module_row["module_api_name"],
                "status": "FAILED_TERMINAL",
                "errorCode": bulk_row.get("controlled_error_code"),
                "cached": True,
                "crmApiCalls": 0,
                "creditsConsumed": 0,
            },
            409,
        )
    if bulk_status not in {"SUBMITTED", "PROCESSING"}:
        return json_response(
            {
                "error": {
                    "code": "BULK_JOB_STATE_CONFLICT",
                    "message": f"Bulk Read status cannot be refreshed from state {bulk_status}",
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
                    "message": "The submitted Bulk Read job has no Zoho job identifier",
                }
            },
            409,
        )

    next_retry_value = bulk_row.get("next_retry_at")
    if next_retry_value:
        try:
            retry_at = from_catalyst_datetime(next_retry_value)
            now_utc = datetime.now(timezone.utc)
            if retry_at > now_utc:
                retry_after = max(1, int((retry_at - now_utc).total_seconds()))
                response = json_response(
                    {
                        "scanId": scan_id,
                        "bulkJobId": bulk_job_id,
                        "module": module_row["module_api_name"],
                        "status": bulk_status,
                        "pollingDeferred": True,
                        "retryAfterSeconds": retry_after,
                        "crmApiCalls": 0,
                        "creditsConsumed": 0,
                    },
                    429,
                )
                response.headers["Retry-After"] = str(retry_after)
                return response
        except (TypeError, ValueError):
            logger.warning("Ignoring invalid next_retry_at for Bulk Read job %s", bulk_job_id)

    try:
        access_token, api_domain, token_refreshed = get_connection_access_token(
            datastore, connection_row
        )
    except DiscoveryError as exc:
        return json_response(
            {"error": {"code": exc.code, "message": str(exc)}}, 502
        )

    try:
        provider_response = requests.get(
            f"{api_domain}/crm/bulk/{API_VERSION}/read/{zoho_job_id}",
            headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
            timeout=20,
        )
    except requests.RequestException as exc:
        logger.exception("Zoho status check failed for Bulk Read job %s: %s", bulk_job_id, exc)
        return json_response(
            {
                "error": {
                    "code": "ZOHO_STATUS_CHECK_FAILED",
                    "message": "Zoho did not return the Bulk Read job status",
                },
                "crmApiCallsAttempted": 1,
                "creditsPossiblyConsumed": 1,
            },
            502,
        )

    if not provider_response.ok:
        logger.error(
            "Zoho Bulk Read status rejected for %s status=%s body=%s",
            bulk_job_id,
            provider_response.status_code,
            provider_response.text[:1000],
        )
        return json_response(
            {
                "error": {
                    "code": f"ZOHO_STATUS_HTTP_{provider_response.status_code}",
                    "message": "Zoho rejected the Bulk Read status request",
                },
                "crmApiCalls": 1,
                "creditsConsumed": 1,
            },
            502,
        )

    try:
        provider_payload = provider_response.json()
        provider_item = provider_payload["data"][0]
        provider_state = str(provider_item["state"]).upper()
        if str(provider_item.get("id")) != str(zoho_job_id):
            raise ValueError("Zoho returned a different job identifier")
    except (TypeError, ValueError, KeyError, IndexError, json.JSONDecodeError) as exc:
        logger.exception("Invalid Zoho status response for Bulk Read job %s: %s", bulk_job_id, exc)
        return json_response(
            {
                "error": {
                    "code": "ZOHO_STATUS_RESPONSE_INVALID",
                    "message": "Zoho returned an unrecognized Bulk Read status response",
                },
                "crmApiCalls": 1,
                "creditsConsumed": 1,
            },
            502,
        )

    bulk_table = datastore.table("bulk_read_jobs")
    module_table = datastore.table("scan_module_runs")
    if provider_state in {"ADDED", "QUEUED", "IN PROGRESS"}:
        next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=60)
        try:
            bulk_table.update_row(
                {
                    "ROWID": bulk_row["ROWID"],
                    "status": "PROCESSING",
                    "next_retry_at": to_catalyst_column_datetime(next_retry_at),
                    "controlled_error_code": "",
                }
            )
            module_table.update_row(
                {"ROWID": module_row["ROWID"], "status": "PROCESSING"}
            )
        except Exception as exc:  # noqa: BLE001 - provider call has already happened
            logger.exception("Could not persist pending status for %s: %s", bulk_job_id, exc)
            return json_response(
                {
                    "error": {
                        "code": "BULK_STATUS_PERSIST_FAILED",
                        "message": "Zoho status was read but could not be stored",
                    },
                    "providerState": provider_state,
                    "crmApiCalls": 1,
                    "creditsConsumed": 1,
                },
                500,
            )
        return json_response(
            {
                "scanId": scan_id,
                "bulkJobId": bulk_job_id,
                "module": module_row["module_api_name"],
                "status": "PROCESSING",
                "providerState": provider_state,
                "retryAfterSeconds": 60,
                "tokenRefreshed": token_refreshed,
                "crmApiCalls": 1,
                "creditsConsumed": 1,
            }
        )

    if provider_state == "COMPLETED":
        result = provider_item.get("result") or {}
        try:
            provider_record_count = int(result.get("count") or 0)
            more_records = bool(result.get("more_records"))
            next_page_token = result.get("next_page_token")
            download_url = result.get("download_url")
            if not download_url:
                raise ValueError("Completed Zoho job has no download URL")
            if more_records and not next_page_token:
                raise ValueError("Completed Zoho job has no next-page token")
        except (TypeError, ValueError) as exc:
            logger.exception("Invalid completed result for Bulk Read job %s: %s", bulk_job_id, exc)
            return json_response(
                {
                    "error": {
                        "code": "ZOHO_COMPLETED_RESULT_INVALID",
                        "message": "Zoho returned incomplete Bulk Read result details",
                    },
                    "crmApiCalls": 1,
                    "creditsConsumed": 1,
                },
                502,
            )

        completed_at = to_catalyst_column_datetime(datetime.now(timezone.utc))
        bulk_update = {
            "ROWID": bulk_row["ROWID"],
            "status": "READY_TO_DOWNLOAD",
            "provider_record_count": provider_record_count,
            "provider_completed_at": completed_at,
            "controlled_error_code": "",
        }
        if next_page_token:
            bulk_update["next_page_token"] = next_page_token
        try:
            bulk_table.update_row(bulk_update)
            module_table.update_row(
                {
                    "ROWID": module_row["ROWID"],
                    "status": "READY_TO_DOWNLOAD",
                    "expected_record_count": provider_record_count,
                }
            )
        except Exception as exc:  # noqa: BLE001 - provider call has already happened
            logger.exception("Could not persist completed status for %s: %s", bulk_job_id, exc)
            return json_response(
                {
                    "error": {
                        "code": "BULK_STATUS_PERSIST_FAILED",
                        "message": "Zoho completion was read but could not be stored",
                    },
                    "providerState": provider_state,
                    "providerRecordCount": provider_record_count,
                    "crmApiCalls": 1,
                    "creditsConsumed": 1,
                },
                500,
            )
        return json_response(
            {
                "scanId": scan_id,
                "bulkJobId": bulk_job_id,
                "module": module_row["module_api_name"],
                "status": "READY_TO_DOWNLOAD",
                "providerState": "COMPLETED",
                "providerRecordCount": provider_record_count,
                "moreRecords": more_records,
                "downloadAvailable": True,
                "tokenRefreshed": token_refreshed,
                "crmApiCalls": 1,
                "creditsConsumed": 1,
            }
        )

    if provider_state == "FAILURE":
        error_message = (provider_item.get("result") or {}).get("error_message") or {}
        provider_error_code = str(error_message.get("code") or "ZOHO_BULK_JOB_FAILED")
        try:
            bulk_table.update_row(
                {
                    "ROWID": bulk_row["ROWID"],
                    "status": "FAILED_TERMINAL",
                    "controlled_error_code": provider_error_code[:100],
                    "provider_completed_at": to_catalyst_column_datetime(
                        datetime.now(timezone.utc)
                    ),
                }
            )
            module_table.update_row(
                {"ROWID": module_row["ROWID"], "status": "FAILED_TERMINAL"}
            )
        except Exception as exc:  # noqa: BLE001 - provider call has already happened
            logger.exception("Could not persist failed status for %s: %s", bulk_job_id, exc)
            return json_response(
                {
                    "error": {
                        "code": "BULK_STATUS_PERSIST_FAILED",
                        "message": "Zoho failure was read but could not be stored",
                    },
                    "providerState": provider_state,
                    "crmApiCalls": 1,
                    "creditsConsumed": 1,
                },
                500,
            )
        return json_response(
            {
                "scanId": scan_id,
                "bulkJobId": bulk_job_id,
                "module": module_row["module_api_name"],
                "status": "FAILED_TERMINAL",
                "providerState": "FAILURE",
                "errorCode": provider_error_code,
                "crmApiCalls": 1,
                "creditsConsumed": 1,
            },
            502,
        )

    logger.error("Unknown Zoho state %s for Bulk Read job %s", provider_state, bulk_job_id)
    return json_response(
        {
            "error": {
                "code": "ZOHO_BULK_STATE_UNKNOWN",
                "message": f"Zoho returned unsupported job state {provider_state}",
            },
            "crmApiCalls": 1,
            "creditsConsumed": 1,
        },
        502,
    )
