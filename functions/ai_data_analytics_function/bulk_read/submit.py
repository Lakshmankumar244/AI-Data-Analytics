"""Submit a planned Zoho Bulk Read job."""

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
from bulk_read.request_builder import build_bulk_read_request

logger = logging.getLogger(__name__)

def submit_bulk_read_job(
    request: Request, datastore, scan_id: str, bulk_job_id: str
):
    """Submit exactly one prepared Bulk Read job to Zoho CRM.

    A provider job may have been created even when our HTTP request times out.
    Such calls are marked SUBMISSION_UNKNOWN and are never retried here.
    """
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
    if scan_row.get("status") not in {"PLANNED", "EXTRACTING"}:
        return json_response(
            {
                "error": {
                    "code": "SCAN_STATE_CONFLICT",
                    "message": f"Bulk Read cannot be submitted from state {scan_row.get('status')}",
                }
            },
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
    if bulk_status == "SUBMITTED" and bulk_row.get("zoho_job_id"):
        return json_response(
            {
                "scanId": scan_id,
                "bulkJobId": bulk_job_id,
                "module": module_row["module_api_name"],
                "status": "SUBMITTED",
                "zohoJobId": bulk_row["zoho_job_id"],
                "alreadySubmitted": True,
                "crmApiCalls": 0,
                "creditsConsumed": 0,
            }
        )
    if bulk_status in {"SUBMITTING", "SUBMISSION_UNKNOWN"}:
        return json_response(
            {
                "error": {
                    "code": "BULK_SUBMISSION_RETRY_BLOCKED",
                    "message": (
                        f"Job is {bulk_status}; automatic retry is blocked to avoid "
                        "creating a duplicate paid Zoho job"
                    ),
                }
            },
            409,
        )
    if bulk_status != "PLANNED":
        return json_response(
            {
                "error": {
                    "code": "BULK_JOB_STATE_CONFLICT",
                    "message": f"Bulk Read job cannot be submitted from state {bulk_status}",
                }
            },
            409,
        )

    try:
        request_body = build_bulk_read_request(scan_row, module_row)
        access_token, api_domain, token_refreshed = get_connection_access_token(
            datastore, connection_row
        )
    except DiscoveryError as exc:
        return json_response(
            {"error": {"code": exc.code, "message": str(exc)}}, 502
        )
    except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return json_response(
            {"error": {"code": "INVALID_BULK_PLAN", "message": str(exc)}}, 409
        )

    bulk_table = datastore.table("bulk_read_jobs")
    module_table = datastore.table("scan_module_runs")
    scan_table = datastore.table("scan_jobs")
    submitted_at = to_catalyst_column_datetime(datetime.now(timezone.utc))
    try:
        attempt_count = int(bulk_row.get("attempt_count") or 0) + 1
        bulk_table.update_row(
            {
                "ROWID": bulk_row["ROWID"],
                "status": "SUBMITTING",
                "attempt_count": attempt_count,
                "submitted_at": submitted_at,
                "controlled_error_code": "",
            }
        )
    except Exception as exc:  # noqa: BLE001 - no provider call has happened yet
        logger.exception("Could not lock Bulk Read job %s for submission: %s", bulk_job_id, exc)
        return json_response(
            {
                "error": {
                    "code": "BULK_SUBMISSION_LOCK_FAILED",
                    "message": "Bulk Read submission was not started",
                }
            },
            500,
        )

    try:
        provider_response = requests.post(
            f"{api_domain}/crm/bulk/{API_VERSION}/read",
            headers={
                "Authorization": f"Zoho-oauthtoken {access_token}",
                "Content-Type": "application/json",
            },
            json=request_body,
            timeout=30,
        )
    except requests.RequestException as exc:
        logger.exception(
            "Ambiguous Zoho Bulk Read submission for local job %s: %s",
            bulk_job_id,
            exc,
        )
        bulk_table.update_row(
            {
                "ROWID": bulk_row["ROWID"],
                "status": "SUBMISSION_UNKNOWN",
                "controlled_error_code": "ZOHO_SUBMISSION_OUTCOME_UNKNOWN",
            }
        )
        return json_response(
            {
                "error": {
                    "code": "ZOHO_SUBMISSION_OUTCOME_UNKNOWN",
                    "message": (
                        "Zoho did not return a conclusive response. Do not retry this job."
                    ),
                },
                "crmApiCallsAttempted": 1,
                "creditsPossiblyConsumed": 50,
            },
            502,
        )

    if not provider_response.ok:
        logger.error(
            "Zoho rejected Bulk Read job %s with status=%s body=%s",
            bulk_job_id,
            provider_response.status_code,
            provider_response.text[:1000],
        )
        rejected_status = (
            "PAUSED_RETRYABLE"
            if provider_response.status_code == 429 or provider_response.status_code >= 500
            else "FAILED_TERMINAL"
        )
        error_code = f"ZOHO_BULK_HTTP_{provider_response.status_code}"
        bulk_table.update_row(
            {
                "ROWID": bulk_row["ROWID"],
                "status": rejected_status,
                "controlled_error_code": error_code,
            }
        )
        return json_response(
            {
                "error": {
                    "code": error_code,
                    "message": "Zoho rejected the Bulk Read submission",
                },
                "crmApiCalls": 1,
                "creditsConsumed": 50,
            },
            502,
        )

    try:
        provider_payload = provider_response.json()
        provider_item = provider_payload["data"][0]
        zoho_job_id = provider_item["details"]["id"]
        if provider_item.get("status") != "success" or not zoho_job_id:
            raise ValueError("Zoho did not return a successful job identifier")
    except (TypeError, ValueError, KeyError, IndexError, json.JSONDecodeError) as exc:
        logger.exception(
            "Unrecognized successful Zoho response for local job %s: %s",
            bulk_job_id,
            exc,
        )
        bulk_table.update_row(
            {
                "ROWID": bulk_row["ROWID"],
                "status": "SUBMISSION_UNKNOWN",
                "controlled_error_code": "ZOHO_SUBMISSION_RESPONSE_INVALID",
            }
        )
        return json_response(
            {
                "error": {
                    "code": "ZOHO_SUBMISSION_RESPONSE_INVALID",
                    "message": "Zoho accepted the request but returned an unrecognized response",
                },
                "crmApiCalls": 1,
                "creditsConsumed": 50,
            },
            502,
        )

    try:
        bulk_table.update_row(
            {
                "ROWID": bulk_row["ROWID"],
                "zoho_job_id": str(zoho_job_id),
                "status": "SUBMITTED",
                "controlled_error_code": "",
            }
        )
        module_table.update_row(
            {"ROWID": module_row["ROWID"], "status": "SUBMITTED"}
        )
        scan_table.update_row(
            {
                "ROWID": scan_row["ROWID"],
                "status": "EXTRACTING",
                "controlled_error_code": "",
            }
        )
    except Exception as exc:  # noqa: BLE001 - the Zoho job already exists
        logger.exception(
            "Zoho job %s exists but local persistence failed for %s: %s",
            zoho_job_id,
            bulk_job_id,
            exc,
        )
        try:
            bulk_table.update_row(
                {
                    "ROWID": bulk_row["ROWID"],
                    "status": "SUBMISSION_UNKNOWN",
                    "controlled_error_code": "ZOHO_JOB_PERSIST_FAILED",
                }
            )
        except Exception:  # noqa: BLE001 - original persistence error is primary
            logger.exception("Could not mark local job %s as unknown", bulk_job_id)
        return json_response(
            {
                "error": {
                    "code": "ZOHO_JOB_PERSIST_FAILED",
                    "message": "Zoho created the job but its identifier could not be stored",
                },
                "zohoJobId": str(zoho_job_id),
                "crmApiCalls": 1,
                "creditsConsumed": 50,
            },
            500,
        )

    return json_response(
        {
            "scanId": scan_id,
            "bulkJobId": bulk_job_id,
            "module": module_row["module_api_name"],
            "status": "SUBMITTED",
            "zohoJobId": str(zoho_job_id),
            "alreadySubmitted": False,
            "tokenRefreshed": token_refreshed,
            "crmApiCalls": 1,
            "creditsConsumed": 50,
        },
        201,
    )
