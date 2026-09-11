"""Scan creation and CRM metadata discovery routes."""

import json
import logging
import uuid
from datetime import timedelta

import zcatalyst_sdk
from flask import Request

from common.core import (
    API_VERSION,
    BASE_FIELD_ALLOWLIST,
    FIELD_PLAN_VERSION,
    ROLLING_RANGE_DAYS,
    RULE_VERSION,
    canonical_hash,
    from_catalyst_datetime,
    get_current_user_id,
    json_response,
    to_catalyst_column_datetime,
    validate_scan_config,
)
from connections.routes import get_connection_access_token
from connections.repository import find_active_connection
from pipeline.orchestrate_enqueue import enqueue_orchestrate_scan
from scans.discover import discover_scan
from zoho.client import (
    build_count_criteria,
    fetch_record_count,
    has_modified_records_since,
)

logger = logging.getLogger(__name__)

ACTIVE_SCAN_STATUSES = frozenset(
    {
        "CREATED",
        "AUTH_VALIDATING",
        "DISCOVERING",
        "PLANNED",
        "EXTRACTING",
        "PROCESSING",
        "PAUSED_RETRYABLE",
    }
)
CURRENT_DOMAIN_SCHEMA_VERSION = "quality-domains-v2"


def _scan_modules(zcql, scan_row_id):
    results = zcql.execute_query(
        f"select * from scan_module_runs where scan_row_id = {int(scan_row_id)}"
    )
    return [item["scan_module_runs"] for item in results]


def _same_range_policy(scan_row, range_id):
    previous_from = scan_row.get("from_utc")
    if range_id == "all":
        return not previous_from
    days = ROLLING_RANGE_DAYS.get(range_id)
    if not days or not previous_from or not scan_row.get("to_utc"):
        return False
    try:
        duration = from_catalyst_datetime(scan_row["to_utc"]) - from_catalyst_datetime(
            previous_from
        )
    except (TypeError, ValueError):
        return False
    return abs(duration - timedelta(days=days)) <= timedelta(minutes=1)


def _matching_scans(zcql, connection_row_id, config):
    results = zcql.execute_query(
        "select * from scan_jobs where "
        f"connection_row_id = {int(connection_row_id)} "
        "order by CREATEDTIME desc limit 20"
    )
    requested_modules = set(config["modules"])
    active = None
    completed = None
    completed_modules = None
    for item in results:
        candidate = item["scan_jobs"]
        status = str(candidate.get("status") or "")
        if status not in ACTIVE_SCAN_STATUSES and status != "COMPLETED":
            continue
        if (
            candidate.get("clock_field") != config["clock_field"]
            or candidate.get("depth_policy") != config["depth"]
            or not _same_range_policy(candidate, config["range_id"])
        ):
            continue
        module_rows = _scan_modules(zcql, candidate["ROWID"])
        if {
            str(row.get("module_api_name") or "") for row in module_rows
        } != requested_modules:
            continue
        if status in ACTIVE_SCAN_STATUSES and active is None:
            active = candidate
        elif status == "COMPLETED" and completed is None:
            completed = candidate
            completed_modules = module_rows
        if active is not None and completed is not None:
            break
    return active, completed, completed_modules


def _has_current_domain_results(zcql, scan_row_id, modules):
    results = zcql.execute_query(
        "select module_api_name,metric_group,status,schema_version from analytics_results where "
        f"scan_row_id = {int(scan_row_id)}"
    )
    measured = {
        str(item["analytics_results"].get("module_api_name") or "")
        for item in results
        if item["analytics_results"].get("metric_group") == "domains"
        and item["analytics_results"].get("status") == "COMPUTED"
        and item["analytics_results"].get("schema_version")
        == CURRENT_DOMAIN_SCHEMA_VERSION
    }
    return set(modules) <= measured


def _zoho_time(value):
    return value.isoformat(timespec="seconds")


def _scope_conditions(config):
    conditions = []
    if config["from_utc"] is not None:
        conditions.append(
            (config["clock_field"], "greater_equal", _zoho_time(config["from_utc"]))
        )
    conditions.append(
        (config["clock_field"], "less_than", _zoho_time(config["to_utc"]))
    )
    return conditions


def _fetch_scoped_module_counts(access_token, api_domain, config):
    criteria = build_count_criteria(_scope_conditions(config))
    return {
        module_name: fetch_record_count(
            access_token, api_domain, module_name, criteria
        )
        for module_name in config["modules"]
    }


def _unchanged_since_previous(
    access_token,
    api_domain,
    config,
    previous_scan,
    previous_modules,
    scoped_counts,
):
    previous_to = from_catalyst_datetime(previous_scan["to_utc"])
    previous_counts = {
        str(row.get("module_api_name") or ""): int(row.get("records_processed") or 0)
        for row in previous_modules
    }
    module_checks = []
    for module_name in config["modules"]:
        scoped_count = int(scoped_counts.get(module_name) or 0)
        modified = has_modified_records_since(
            access_token,
            api_domain,
            module_name,
            _zoho_time(previous_to),
        )
        changed = (
            scoped_count != previous_counts.get(module_name) or modified
        )
        module_checks.append(
            {
                "apiName": module_name,
                "recordCount": scoped_count,
                "modifiedSincePrevious": modified,
                "changed": changed,
            }
        )
    return not any(item["changed"] for item in module_checks), module_checks


def _reused_scan_response(scan_row, modules, reason, checks=None):
    return {
        "scanId": scan_row["scan_id"],
        "status": scan_row["status"],
        "moduleCount": len(modules),
        "modules": modules,
        "bulkReadSubmitted": scan_row["status"] not in {"CREATED", "DISCOVERING", "PLANNED"},
        "reused": True,
        "reuseReason": reason,
        "changeChecks": checks or [],
        "reportContext": {
            "clock": scan_row.get("clock_field"),
            "fromUtc": str(scan_row.get("from_utc") or ""),
            "toUtc": str(scan_row.get("to_utc") or ""),
            "depth": scan_row.get("depth_policy"),
        },
    }

def create_scan(request: Request, datastore):
    user_id = get_current_user_id(request)
    zcql = zcatalyst_sdk.initialize().zcql()
    connection_row = find_active_connection(zcql, user_id)
    if not connection_row:
        return json_response(
            {
                "error": {
                    "code": "ZOHO_CONNECTION_REQUIRED",
                    "message": "Connect Zoho CRM before creating a scan",
                }
            },
            409,
        )

    try:
        config = validate_scan_config(request.get_json(silent=True), connection_row)
    except PermissionError as exc:
        return json_response(
            {"error": {"code": "MODULE_NOT_ACCESSIBLE", "message": str(exc)}}, 403
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return json_response(
            {"error": {"code": "INVALID_SCAN_CONFIG", "message": str(exc)}}, 400
        )

    active_scan, previous_scan, previous_modules = _matching_scans(
        zcql, connection_row["ROWID"], config
    )
    change_checks = []
    live_counts = {}
    if active_scan:
        return json_response(
            _reused_scan_response(
                active_scan,
                config["modules"],
                "ACTIVE_EQUIVALENT_SCAN",
            )
        )

    try:
        access_token, api_domain, _token_refreshed = get_connection_access_token(
            datastore, connection_row
        )
        live_counts = _fetch_scoped_module_counts(access_token, api_domain, config)
        if (
            previous_scan
            and previous_modules
            and _has_current_domain_results(
                zcql, previous_scan["ROWID"], config["modules"]
            )
        ):
            unchanged, change_checks = _unchanged_since_previous(
                access_token,
                api_domain,
                config,
                previous_scan,
                previous_modules,
                live_counts,
            )
            if unchanged:
                return json_response(
                    _reused_scan_response(
                        previous_scan,
                        config["modules"],
                        "NO_CRM_CHANGES",
                        change_checks,
                    )
                )
    except Exception as exc:  # noqa: BLE001 - uncertainty must allow a fresh scan
        logger.warning(
            "Live CRM count check failed; creating a fresh scan instead: %s", exc
        )

    scan_id = f"scan_{uuid.uuid4().hex}"
    organization_timezone = connection_row.get("organization_timezone") or "UTC"
    field_allowlist = list(BASE_FIELD_ALLOWLIST)
    field_plan_hash = canonical_hash(
        {"version": FIELD_PLAN_VERSION, "fields": field_allowlist}
    )
    manifest = {
        "scan_id": scan_id,
        "connection_row_id": str(connection_row["ROWID"]),
        "modules": sorted(config["modules"]),
        "clock_field": config["clock_field"],
        "range_id": config["range_id"],
        "from_utc": config["from_utc"].isoformat() if config["from_utc"] else None,
        "to_utc": config["to_utc"].isoformat(),
        "depth_policy": config["depth"],
        "organization_timezone": organization_timezone,
        "api_version": API_VERSION,
        "rule_version": RULE_VERSION,
        "field_plan_version": FIELD_PLAN_VERSION,
    }
    manifest_hash = canonical_hash(manifest)

    scan_row_data = {
        "scan_id": scan_id,
        "connection_row_id": connection_row["ROWID"],
        "status": "CREATED",
        "clock_field": config["clock_field"],
        "to_utc": to_catalyst_column_datetime(config["to_utc"]),
        "depth_policy": config["depth"],
        "organization_timezone": organization_timezone,
        "api_version": API_VERSION,
        "rule_version": RULE_VERSION,
        "field_plan_version": FIELD_PLAN_VERSION,
        "manifest_hash": manifest_hash,
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
        for module_api_name in config["modules"]:
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
                    "field_allowlist_json": json.dumps(field_allowlist),
                    "field_plan_hash": field_plan_hash,
                    "criteria_hash": criteria_hash,
                    "bulk_jobs_planned": 0,
                    "bulk_jobs_completed": 0,
                    "records_downloaded": 0,
                    "records_processed": 0,
                    "batches_completed": 0,
                    "expected_record_count": int(live_counts.get(module_api_name) or 0),
                }
            )
        module_table.insert_rows(module_rows)
    except Exception as exc:  # noqa: BLE001 - return only a controlled error to the client
        logger.exception("Failed to persist scan plan %s", scan_id)
        logger.error(
            "Scan persistence exception type=%s message=%s args=%r",
            type(exc).__name__,
            str(exc),
            exc.args,
        )
        sdk_response = getattr(exc, "response", None)
        if sdk_response is not None:
            logger.error(
                "Catalyst Data Store response status=%s body=%s",
                getattr(sdk_response, "status_code", None),
                getattr(sdk_response, "text", "")[:1000],
            )
        if "inserted_scan" in locals():
            try:
                scan_table.update_row(
                    {
                        "ROWID": inserted_scan["ROWID"],
                        "status": "FAILED_TERMINAL",
                        "controlled_error_code": "SCAN_PLAN_PERSIST_FAILED",
                    }
                )
            except Exception:  # noqa: BLE001 - original persistence error is primary
                logger.exception("Failed to mark scan %s as failed", scan_id)
        return json_response(
            {
                "error": {
                    "code": "SCAN_PLAN_PERSIST_FAILED",
                    "message": "The scan plan could not be stored",
                }
            },
            500,
        )

    try:
        enqueue_result = enqueue_orchestrate_scan(
            zcatalyst_sdk.initialize(), datastore, inserted_scan
        )
        logger.info(
            "SCAN_PROFILE %s",
            json.dumps(
                {
                    "scope": "ORCHESTRATE_SCAN",
                    "stage": "create_scan_enqueue",
                    "scanId": scan_id,
                    "ok": enqueue_result.get("ok"),
                    "submitted": enqueue_result.get("submitted"),
                    "alreadyActive": enqueue_result.get("alreadyActive"),
                    "code": enqueue_result.get("code"),
                    "taskId": (enqueue_result.get("task") or {}).get("task_id"),
                },
                default=str,
            ),
        )
    except Exception:
        logger.exception(
            "Could not enqueue ORCHESTRATE_SCAN for scan %s", scan_id
        )

    return json_response(
        {
            "scanId": scan_id,
            "status": "CREATED",
            "moduleCount": len(config["modules"]),
            "modules": config["modules"],
            "bulkReadSubmitted": False,
            "reused": False,
            "changeChecks": change_checks,
            "changedModules": [
                item["apiName"] for item in change_checks if item["changed"]
            ],
            "reportContext": {
                "clock": config["clock_field"],
                "fromUtc": manifest["from_utc"] or "",
                "toUtc": manifest["to_utc"],
                "depth": config["depth"],
            },
        },
        201,
    )
