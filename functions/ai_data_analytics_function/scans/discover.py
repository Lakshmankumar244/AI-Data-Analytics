"""CRM metadata discovery for a persisted scan plan."""

import json
import logging

import zcatalyst_sdk
from flask import Request

from common.core import (
    API_VERSION,
    DISCOVERED_FIELD_PLAN_VERSION,
    DiscoveryError,
    RULE_VERSION,
    canonical_hash,
    json_response,
    to_zoho_datetime,
)
from connections.access import resolve_action_connection
from connections.token import get_connection_access_token
from zoho.client import (
    build_count_criteria,
    build_field_allowlist,
    build_field_metadata,
    fetch_module_fields,
    fetch_organization_metadata,
    fetch_record_count,
)
from zoho.user_directory import sync_connection_user_directory

logger = logging.getLogger(__name__)


def _scope_conditions_from_scan_row(scan_row):
    conditions = []
    clock_field = scan_row["clock_field"]
    from_utc = scan_row.get("from_utc")
    if from_utc:
        conditions.append(
            (clock_field, "greater_equal", to_zoho_datetime(from_utc))
        )
    conditions.append(
        (clock_field, "less_than", to_zoho_datetime(scan_row["to_utc"]))
    )
    return conditions


def discover_scan(request: Request, datastore, scan_id: str, connection_row=None):
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

    connection_row = resolve_action_connection(
        zcql, scan_row, request=request, connection_row=connection_row
    )
    if not connection_row:
        return json_response(
            {"error": {"code": "ZOHO_CONNECTION_REQUIRED", "message": "Reconnect Zoho CRM"}},
            409,
        )
    if scan_row.get("status") == "PLANNED":
        return json_response(
            {
                "scanId": scan_id,
                "status": "PLANNED",
                "alreadyDiscovered": True,
                "crmApiCalls": 0,
                "bulkReadSubmitted": False,
            }
        )
    if scan_row.get("status") not in {"CREATED", "PAUSED_RETRYABLE", "DISCOVERING"}:
        return json_response(
            {
                "error": {
                    "code": "SCAN_STATE_CONFLICT",
                    "message": f"Scan cannot be discovered from state {scan_row.get('status')}",
                }
            },
            409,
        )

    scan_table = datastore.table("scan_jobs")
    module_table = datastore.table("scan_module_runs")
    scan_table.update_row({"ROWID": scan_row["ROWID"], "status": "AUTH_VALIDATING"})

    try:
        access_token, api_domain, token_refreshed = get_connection_access_token(
            datastore, connection_row
        )
        scan_table.update_row({"ROWID": scan_row["ROWID"], "status": "DISCOVERING"})
        organization = fetch_organization_metadata(access_token, api_domain)
        directory_sync = sync_connection_user_directory(
            datastore, zcql, connection_row, access_token, api_domain
        )

        scan_row_id = str(scan_row["ROWID"])
        if not scan_row_id.isdigit():
            raise DiscoveryError("INVALID_SCAN_ROW_ID", "Scan storage identifier is invalid")
        module_rows = zcql.execute_query(
            f"select * from scan_module_runs where scan_row_id = {scan_row_id}"
        )
        if not module_rows:
            raise DiscoveryError("MODULE_PLAN_MISSING", "The scan has no module plans")

        discovered_modules = []
        field_plan_hashes = {}
        count_criteria = build_count_criteria(_scope_conditions_from_scan_row(scan_row))
        for result in module_rows:
            module_row = result["scan_module_runs"]
            module_api_name = module_row["module_api_name"]
            fields = fetch_module_fields(access_token, api_domain, module_api_name)
            allowlist = build_field_allowlist(fields)
            field_metadata = build_field_metadata(fields, allowlist)
            plan_hash = canonical_hash(
                {
                    "version": DISCOVERED_FIELD_PLAN_VERSION,
                    "module": module_api_name,
                    "fields": allowlist,
                    "fieldMetadata": field_metadata,
                }
            )
            try:
                expected_record_count = fetch_record_count(
                    access_token,
                    api_domain,
                    module_api_name,
                    count_criteria,
                )
            except Exception as exc:  # noqa: BLE001 - keep the count captured at scan create
                logger.warning(
                    "Could not refresh live record count for %s: %s",
                    module_api_name,
                    exc,
                )
                expected_record_count = int(module_row.get("expected_record_count") or 0)
            module_table.update_row(
                {
                    "ROWID": module_row["ROWID"],
                    "field_allowlist_json": json.dumps(allowlist),
                    "field_metadata_json": json.dumps(
                        field_metadata, separators=(",", ":")
                    ),
                    "field_plan_hash": plan_hash,
                    "status": "PLANNED",
                    "expected_record_count": expected_record_count,
                }
            )
            field_plan_hashes[module_api_name] = plan_hash
            discovered_modules.append(
                {"apiName": module_api_name, "selectedFieldCount": len(allowlist)}
            )

        final_manifest_hash = canonical_hash(
            {
                "scan_id": scan_id,
                "connection_row_id": str(connection_row["ROWID"]),
                "modules": sorted(field_plan_hashes),
                "field_plan_hashes": field_plan_hashes,
                "clock_field": scan_row["clock_field"],
                "from_utc": scan_row.get("from_utc"),
                "to_utc": scan_row["to_utc"],
                "depth_policy": scan_row["depth_policy"],
                "organization_timezone": organization["time_zone"],
                "api_version": API_VERSION,
                "rule_version": RULE_VERSION,
                "field_plan_version": DISCOVERED_FIELD_PLAN_VERSION,
            }
        )
        scan_table.update_row(
            {
                "ROWID": scan_row["ROWID"],
                "status": "PLANNED",
                "organization_timezone": organization["time_zone"],
                "field_plan_version": DISCOVERED_FIELD_PLAN_VERSION,
                "manifest_hash": final_manifest_hash,
                "controlled_error_code": "",
            }
        )
        datastore.table("zoho_connections").update_row(
            {
                "ROWID": connection_row["ROWID"],
                "zoho_org_id": organization.get("id", ""),
                "organization_name": organization.get("company_name", ""),
            }
        )
    except DiscoveryError as exc:
        logger.exception("Discovery failed for scan %s with %s", scan_id, exc.code)
        scan_table.update_row(
            {
                "ROWID": scan_row["ROWID"],
                "status": "PAUSED_RETRYABLE",
                "controlled_error_code": exc.code,
            }
        )
        return json_response(
            {"error": {"code": exc.code, "message": str(exc)}}, 502
        )
    except Exception as exc:  # noqa: BLE001 - keep provider/storage details server-side
        logger.exception("Unexpected discovery failure for scan %s: %s", scan_id, exc)
        scan_table.update_row(
            {
                "ROWID": scan_row["ROWID"],
                "status": "PAUSED_RETRYABLE",
                "controlled_error_code": "DISCOVERY_FAILED",
            }
        )
        return json_response(
            {
                "error": {
                    "code": "DISCOVERY_FAILED",
                    "message": "Scan discovery could not be completed",
                }
            },
            500,
        )

    return json_response(
        {
            "scanId": scan_id,
            "status": "PLANNED",
            "organizationTimezone": organization["time_zone"],
            "modules": discovered_modules,
            "tokenRefreshed": token_refreshed,
            "crmApiCalls": 1 + len(discovered_modules) + directory_sync["apiCalls"],
            "userDirectory": {
                "refreshed": directory_sync["refreshed"],
                "apiCalls": directory_sync["apiCalls"],
                "userCount": directory_sync["userCount"],
                "warning": directory_sync["warning"],
            },
            "bulkReadSubmitted": False,
        }
    )
