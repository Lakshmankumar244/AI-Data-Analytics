"""Salesforce scan control-plane: create scan_jobs without Zoho extraction.

Schema (Catalyst Data Store; create the column in the console — this repo has
no table-migration mechanism):

    scan_jobs.crm_provider  text  "salesforce" | omitted/empty treated as "zoho"

Existing Zoho inserts omit the column. Salesforce inserts set crm_provider so
connection_row_id is never resolved against zoho_connections by ROWID collision.

Do not enqueue ORCHESTRATE_SCAN for Salesforce scans. The worker still assumes
Zoho Bulk Read and its connections/repository still binds connection_row_id to
zoho_connections. When Salesforce extraction is implemented:

    1. Guard the worker discover/orchestrate path on crm_provider.
    2. Copy scan_crm_provider into the worker connections repository.
    3. Enqueue a Salesforce extraction job instead of Zoho ORCHESTRATE_SCAN.
"""

import json
import logging
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

SALESFORCE_CRM_PROVIDER = "salesforce"
SALESFORCE_SCAN_CLOCK_FIELDS = {
    "created": "CreatedDate",
    "modified": "LastModifiedDate",
}


def resolve_active_crm_connection(zcql, user_id):
    """Return (provider, row) for the exclusive-active CRM connection."""
    from connections.repository import find_active_connection
    from salesforce.oauth import find_active_salesforce_connection

    salesforce_row = find_active_salesforce_connection(zcql, user_id)
    zoho_row = find_active_connection(zcql, user_id)
    if salesforce_row and zoho_row:
        salesforce_key = (
            str(salesforce_row.get("last_selected_at") or ""),
            str(salesforce_row.get("ROWID") or ""),
        )
        zoho_key = (
            str(zoho_row.get("last_selected_at") or ""),
            str(zoho_row.get("ROWID") or ""),
        )
        if zoho_key > salesforce_key:
            return "zoho", zoho_row
        return SALESFORCE_CRM_PROVIDER, salesforce_row
    if salesforce_row:
        return SALESFORCE_CRM_PROVIDER, salesforce_row
    if zoho_row:
        return "zoho", zoho_row
    return None, None


def is_salesforce_scan(scan_row):
    from connections.repository import scan_crm_provider

    return scan_crm_provider(scan_row) == SALESFORCE_CRM_PROVIDER


def require_salesforce_timezone(organization: dict) -> str:
    """Fail closed: do not substitute UTC or the server timezone."""
    time_zone = str((organization or {}).get("timeZone") or "").strip()
    if not time_zone:
        raise ValueError("Salesforce organization timezone is unavailable")
    try:
        ZoneInfo(time_zone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Salesforce organization timezone is unavailable") from exc
    return time_zone


def accessible_salesforce_object_names(objects: list) -> set:
    names = set()
    for item in objects or []:
        if not isinstance(item, dict):
            continue
        api_name = str(item.get("apiName") or "").strip()
        if api_name:
            names.add(api_name)
    return names


def build_salesforce_module_field_plan(describe_payload: dict, clock_field: str):
    """Salesforce-native allowlist/metadata; clock field must exist on the object."""
    from salesforce.describe import describe_salesforce_fields

    described = describe_salesforce_fields(describe_payload)
    allowlist = list(described["allowlist"])
    if clock_field not in allowlist:
        raise ValueError(
            f"Salesforce object {described['object']['apiName']} has no {clock_field} field"
        )
    return allowlist, described["fields"]


def create_salesforce_scan(
    datastore,
    zcql,
    connection_row,
    payload,
    matching_scans=None,
    reused_scan_response=None,
):
    """Persist a Salesforce scan plan and leave it CREATED without worker enqueue."""
    from common.core import (
        API_VERSION,
        DISCOVERED_FIELD_PLAN_VERSION,
        DiscoveryError,
        RULE_VERSION,
        canonical_hash,
        to_catalyst_column_datetime,
        validate_scan_config,
    )
    from salesforce.client import (
        fetch_accessible_sobjects,
        fetch_salesforce_organization,
        get_salesforce_access_token,
        persist_salesforce_organization_name,
    )
    from salesforce.describe import fetch_sobject_describe

    try:
        access_token, instance_url = get_salesforce_access_token(
            datastore, connection_row
        )
        organization = fetch_salesforce_organization(
            access_token, instance_url, connection_row
        )
        persist_salesforce_organization_name(datastore, connection_row, organization)
        time_zone = require_salesforce_timezone(organization)
        objects = fetch_accessible_sobjects(access_token, instance_url)
        config = validate_scan_config(
            payload,
            connection_row,
            clock_fields=SALESFORCE_SCAN_CLOCK_FIELDS,
            accessible_names=accessible_salesforce_object_names(objects),
        )
    except PermissionError as exc:
        return 403, {"error": {"code": "MODULE_NOT_ACCESSIBLE", "message": str(exc)}}
    except DiscoveryError as exc:
        return 502, {"error": {"code": exc.code, "message": str(exc)}}
    except ValueError as exc:
        message = str(exc)
        if "timezone" in message.lower():
            return 502, {
                "error": {
                    "code": "ORGANIZATION_TIMEZONE_MISSING",
                    "message": message,
                }
            }
        return 400, {"error": {"code": "INVALID_SCAN_CONFIG", "message": message}}
    except (TypeError, json.JSONDecodeError) as exc:
        return 400, {"error": {"code": "INVALID_SCAN_CONFIG", "message": str(exc)}}

    if matching_scans:
        active_scan = matching_scans(
            zcql,
            connection_row["ROWID"],
            config,
            crm_provider=SALESFORCE_CRM_PROVIDER,
        )
        if active_scan:
            response_builder = reused_scan_response or (
                lambda scan_row, modules, reason, checks=None: {
                    "scanId": scan_row["scan_id"],
                    "status": scan_row["status"],
                    "modules": modules,
                    "reused": True,
                    "reuseReason": reason,
                }
            )
            return 200, response_builder(
                active_scan, config["modules"], "ACTIVE_EQUIVALENT_SCAN"
            )

    try:
        module_plans = []
        for module_api_name in config["modules"]:
            describe_payload = fetch_sobject_describe(
                access_token, instance_url, module_api_name
            )
            allowlist, field_metadata = build_salesforce_module_field_plan(
                describe_payload, config["clock_field"]
            )
            module_plans.append(
                {
                    "module_api_name": module_api_name,
                    "allowlist": allowlist,
                    "field_metadata": field_metadata,
                }
            )
    except DiscoveryError as exc:
        return 502, {"error": {"code": exc.code, "message": str(exc)}}
    except ValueError as exc:
        return 502, {
            "error": {"code": "CLOCK_FIELD_UNAVAILABLE", "message": str(exc)}
        }

    scan_id = f"scan_{uuid.uuid4().hex}"
    field_plan_hashes = {}
    for plan in module_plans:
        field_plan_hashes[plan["module_api_name"]] = canonical_hash(
            {
                "version": DISCOVERED_FIELD_PLAN_VERSION,
                "module": plan["module_api_name"],
                "fields": plan["allowlist"],
                "fieldMetadata": plan["field_metadata"],
            }
        )
    manifest = {
        "scan_id": scan_id,
        "crm_provider": SALESFORCE_CRM_PROVIDER,
        "connection_row_id": str(connection_row["ROWID"]),
        "modules": sorted(config["modules"]),
        "clock_field": config["clock_field"],
        "range_id": config["range_id"],
        "from_utc": config["from_utc"].isoformat() if config["from_utc"] else None,
        "to_utc": config["to_utc"].isoformat(),
        "depth_policy": config["depth"],
        "organization_timezone": time_zone,
        "api_version": API_VERSION,
        "rule_version": RULE_VERSION,
        "field_plan_version": DISCOVERED_FIELD_PLAN_VERSION,
        "field_plan_hashes": field_plan_hashes,
    }
    scan_row_data = {
        "scan_id": scan_id,
        "crm_provider": SALESFORCE_CRM_PROVIDER,
        "connection_row_id": connection_row["ROWID"],
        "status": "CREATED",
        "clock_field": config["clock_field"],
        "to_utc": to_catalyst_column_datetime(config["to_utc"]),
        "depth_policy": config["depth"],
        "organization_timezone": time_zone,
        "api_version": API_VERSION,
        "rule_version": RULE_VERSION,
        "field_plan_version": DISCOVERED_FIELD_PLAN_VERSION,
        "manifest_hash": canonical_hash(manifest),
        "visibility_status": "UNVERIFIED",
        "planned_module_count": len(config["modules"]),
        "completed_module_count": 0,
        "cancel_requested": False,
    }
    if config["from_utc"] is not None:
        scan_row_data["from_utc"] = to_catalyst_column_datetime(config["from_utc"])

    scan_table = datastore.table("scan_jobs")
    module_table = datastore.table("scan_module_runs")
    try:
        inserted_scan = scan_table.insert_row(scan_row_data)
        module_rows = []
        for plan in module_plans:
            module_api_name = plan["module_api_name"]
            criteria_hash = canonical_hash(
                {
                    "module": module_api_name,
                    "clock_field": config["clock_field"],
                    "from_utc": manifest["from_utc"],
                    "to_utc": manifest["to_utc"],
                }
            )
            module_rows.append(
                {
                    "scan_module_id": f"smod_{uuid.uuid4().hex}",
                    "scan_row_id": inserted_scan["ROWID"],
                    "module_key": canonical_hash(
                        {"scan_id": scan_id, "module": module_api_name}
                    ),
                    "module_api_name": module_api_name,
                    "status": "PLANNED",
                    "field_allowlist_json": json.dumps(plan["allowlist"]),
                    "field_metadata_json": json.dumps(
                        plan["field_metadata"], separators=(",", ":")
                    ),
                    "field_plan_hash": field_plan_hashes[module_api_name],
                    "criteria_hash": criteria_hash,
                    "bulk_jobs_planned": 0,
                    "bulk_jobs_completed": 0,
                    "records_downloaded": 0,
                    "records_processed": 0,
                    "batches_completed": 0,
                    "expected_record_count": 0,
                }
            )
        module_table.insert_rows(module_rows)
    except Exception:
        logger.exception("Failed to persist Salesforce scan plan %s", scan_id)
        if "inserted_scan" in locals():
            try:
                scan_table.update_row(
                    {
                        "ROWID": inserted_scan["ROWID"],
                        "status": "FAILED_TERMINAL",
                        "controlled_error_code": "SCAN_PLAN_PERSIST_FAILED",
                    }
                )
            except Exception:
                logger.exception("Failed to mark Salesforce scan %s as failed", scan_id)
        return 500, {
            "error": {
                "code": "SCAN_PLAN_PERSIST_FAILED",
                "message": "The scan plan could not be stored",
            }
        }

    # Do not enqueue ORCHESTRATE_SCAN: the worker still assumes Zoho Bulk Read.
    return 201, {
        "scanId": scan_id,
        "status": "CREATED",
        "crmProvider": SALESFORCE_CRM_PROVIDER,
        "moduleCount": len(config["modules"]),
        "modules": config["modules"],
        "bulkReadSubmitted": False,
        "reused": False,
        "changeChecks": [],
        "changedModules": [],
        "reportContext": {
            "clock": config["clock_field"],
            "fromUtc": manifest["from_utc"] or "",
            "toUtc": manifest["to_utc"],
            "depth": config["depth"],
            "organizationTimezone": time_zone,
        },
    }
