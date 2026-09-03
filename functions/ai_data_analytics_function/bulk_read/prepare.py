"""Plan durable Bulk Read jobs for a scan."""

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

from bulk_read.request_builder import build_bulk_read_request

def prepare_bulk_read(request: Request, datastore, scan_id: str):
    """Persist page-one Bulk Read plans without making any Zoho API call."""
    zcql = zcatalyst_sdk.initialize().zcql()
    safe_scan_id = scan_id.replace("'", "''")
    scan_rows = zcql.execute_query(
        f"select * from scan_jobs where scan_id = '{safe_scan_id}' limit 1"
    )
    if not scan_rows:
        return json_response(
            {"error": {"code": "SCAN_NOT_FOUND", "message": "Scan was not found"}}, 404
        )
    scan_row = scan_rows[0]["scan_jobs"]

    user_id = get_current_user_id(request)
    connection_row = find_scan_connection(zcql, user_id, scan_row)
    if not connection_row:
        return json_response(
            {"error": {"code": "ZOHO_CONNECTION_REQUIRED", "message": "Reconnect Zoho CRM"}},
            409,
        )
    if scan_row.get("status") != "PLANNED":
        return json_response(
            {
                "error": {
                    "code": "SCAN_STATE_CONFLICT",
                    "message": f"Bulk Read cannot be prepared from state {scan_row.get('status')}",
                }
            },
            409,
        )

    scan_row_id = str(scan_row["ROWID"])
    if not scan_row_id.isdigit():
        return json_response(
            {
                "error": {
                    "code": "INVALID_SCAN_ROW_ID",
                    "message": "Scan storage identifier is invalid",
                }
            },
            500,
        )
    module_results = zcql.execute_query(
        f"select * from scan_module_runs where scan_row_id = {scan_row_id}"
    )
    if not module_results:
        return json_response(
            {
                "error": {
                    "code": "MODULE_PLAN_MISSING",
                    "message": "The scan has no module plans",
                }
            },
            409,
        )

    bulk_table = datastore.table("bulk_read_jobs")
    module_table = datastore.table("scan_module_runs")
    plans = []
    created_count = 0
    try:
        for result in module_results:
            module_row = result["scan_module_runs"]
            if module_row.get("status") != "PLANNED":
                raise ValueError(
                    f"Module {module_row.get('module_api_name')} is not in PLANNED state"
                )

            request_body = build_bulk_read_request(scan_row, module_row)
            logical_job_key = canonical_hash(
                {
                    "scan_id": scan_id,
                    "scan_module_id": module_row["scan_module_id"],
                    "field_plan_hash": module_row["field_plan_hash"],
                    "criteria_hash": module_row["criteria_hash"],
                    "page": 1,
                }
            )
            module_row_id = str(module_row["ROWID"])
            if not module_row_id.isdigit():
                raise ValueError("Module storage identifier is invalid")
            existing_rows = zcql.execute_query(
                "select * from bulk_read_jobs where "
                f"scan_module_row_id = {module_row_id} and provider_page = 1 limit 1"
            )
            if existing_rows:
                bulk_row = existing_rows[0]["bulk_read_jobs"]
                if bulk_row.get("logical_job_key") != logical_job_key:
                    return json_response(
                        {
                            "error": {
                                "code": "BULK_PLAN_STALE",
                                "message": (
                                    f"The stored Bulk Read plan for "
                                    f"{module_row['module_api_name']} no longer matches the scan"
                                ),
                            }
                        },
                        409,
                    )
                was_created = False
            else:
                bulk_row = bulk_table.insert_row(
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
                created_count += 1
                was_created = True

            # Also repairs the counter if a previous invocation inserted the
            # job but stopped before updating its parent module row.
            module_table.update_row(
                {"ROWID": module_row["ROWID"], "bulk_jobs_planned": 1}
            )
            plans.append(
                {
                    "bulkJobId": bulk_row["bulk_job_id"],
                    "module": module_row["module_api_name"],
                    "providerPage": 1,
                    "status": bulk_row["status"],
                    "created": was_created,
                    "request": request_body,
                }
            )
    except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        logger.warning("Invalid Bulk Read plan for scan %s: %s", scan_id, exc)
        return json_response(
            {
                "error": {
                    "code": "INVALID_BULK_PLAN",
                    "message": str(exc),
                }
            },
            409,
        )
    except Exception as exc:  # noqa: BLE001 - keep SDK/storage details server-side
        logger.exception("Failed to persist Bulk Read plan for scan %s: %s", scan_id, exc)
        return json_response(
            {
                "error": {
                    "code": "BULK_PLAN_PERSIST_FAILED",
                    "message": "The Bulk Read plan could not be stored",
                }
            },
            500,
        )

    return json_response(
        {
            "scanId": scan_id,
            "status": "PLANNED",
            "plans": plans,
            "plannedJobCount": len(plans),
            "createdJobCount": created_count,
            "alreadyPrepared": created_count == 0,
            "crmApiCalls": 0,
            "estimatedSubmissionCredits": 50 * len(plans),
            "bulkReadSubmitted": False,
        }
    )
