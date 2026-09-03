"""Build a read-only remediation plan from persisted record issues."""

import hashlib
import json
import logging

import zcatalyst_sdk

from analytics.repository import find_analytics_results, find_module_runs, find_owned_scan
from common.core import (
    AuthenticationRequired,
    QUALITY_FIELD_CANDIDATES,
    foreign_row_id,
    get_current_user_id,
    json_response,
    query_list_values,
)


LOGGER = logging.getLogger(__name__)
QUERY_PAGE_SIZE = 300
MAX_ACTIONS = 30
SUPPORTED_RECORD_FINDING_SCHEMAS = frozenset(
    {"record-findings-v1", "record-findings-v2", "record-findings-v3"}
)
SEVERITY_WEIGHT = {"LOW": 1, "MEDIUM": 2, "HIGH": 4, "CRITICAL": 8}
ISSUE_LABELS = {
    "INVALID_EMAIL": "email",
    "INVALID_PHONE": "phone",
    "INVALID_URL": "URL",
    "INVALID_NUMBER": "number",
    "INVALID_DATETIME": "date/time",
}


def _rows(zcql, query, table_name):
    return [item[table_name] for item in zcql.execute_query(query)]


def _integer(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _selected_modules(request):
    modules = []
    for value in query_list_values(request, "module"):
        module = str(value or "").strip()
        if module and len(module) <= 100:
            modules.append(module)
    return set(modules)


def _module_record_counts(result_rows, selected):
    counts = {}
    measured_modules = set()
    finding_candidates = []
    for row in result_rows:
        if row.get("status") != "COMPUTED":
            continue
        module_name = str(row.get("module_api_name") or "")
        if not module_name or (selected and module_name not in selected):
            continue
        if row.get("metric_group") == "record_findings":
            try:
                payload = json.loads(row.get("aggregate_json") or "")
            except (TypeError, ValueError, json.JSONDecodeError):
                payload = {}
            if (
                row.get("schema_version") in SUPPORTED_RECORD_FINDING_SCHEMAS
                and isinstance(payload, dict)
                and payload.get("measured")
            ):
                finding_candidates.append((row, module_name, payload))
        elif row.get("metric_group") == "summary":
            counts[module_name] = max(
                counts.get(module_name, 0), _integer(row.get("source_record_count"))
            )
    preferred_schema = max(
        (
            str(row.get("schema_version") or "")
            for row, _module_name, _payload in finding_candidates
        ),
        default=None,
    )
    aggregate_groups = {}
    for row, module_name, payload in finding_candidates:
        if row.get("schema_version") == preferred_schema:
            measured_modules.add(module_name)
            aggregate_groups[module_name] = payload.get("issueGroups") or []
    return counts, measured_modules, preferred_schema, aggregate_groups


def _priority(issue_type, field_name, coverage, importance):
    if issue_type != "MISSING_VALUE":
        return "HIGH"
    if importance in {"SYSTEM_MANDATORY", "UNIQUE"}:
        return "HIGH"
    if importance == "BUSINESS_CRITICAL":
        return "HIGH" if coverage >= 0.5 else "MEDIUM"
    if importance == "OPTIONAL":
        return "LOW"
    if field_name in QUALITY_FIELD_CANDIDATES and coverage >= 0.5:
        return "HIGH"
    if field_name in QUALITY_FIELD_CANDIDATES or coverage >= 0.25:
        return "MEDIUM"
    return "LOW"


def _action(group, module_name, module_record_count):
    field_name = group["fieldApiName"]
    field_label = group["fieldLabel"]
    issue_type = group["issueType"]
    importance = group["importance"]
    count = group["recordCount"]
    coverage = round(count / module_record_count, 4) if module_record_count else None
    priority = _priority(issue_type, field_name, coverage or 0, importance)
    if issue_type == "MISSING_VALUE":
        prefix = {
            "SYSTEM_MANDATORY": "Complete required",
            "UNIQUE": "Review missing unique",
            "BUSINESS_CRITICAL": "Complete business-critical",
            "OPTIONAL": "Review optional",
        }.get(importance, "Review missing")
        title = f"{prefix} {field_label} values in {module_name}"
        reason = {
            "SYSTEM_MANDATORY": "Zoho CRM marks this field as system-mandatory.",
            "UNIQUE": "Zoho CRM marks this field as unique; verify whether blank values are acceptable.",
            "BUSINESS_CRITICAL": "This field is part of the scan's business-quality policy.",
            "OPTIONAL": "This optional field is included because this was a deep or full scan.",
        }.get(importance, "Complete it where your business process requires the field.")
        count_text = (
            f"{count} of {module_record_count} analyzed records have no {field_label} value."
            if module_record_count
            else f"{count} records have no {field_label} value."
        )
        description = f"{count_text} {reason} No value should be inferred automatically."
        target_state = "incomplete"
    else:
        value_kind = ISSUE_LABELS.get(issue_type, "field")
        title = f"Correct invalid {field_label} values in {module_name}"
        description = (
            f"{count} {value_kind} value{'s' if count != 1 else ''} failed format validation. "
            "Review the source before correcting it; this application has not changed any CRM value."
        )
        target_state = "inaccurate"

    action_key = f"{module_name}:{field_name}:{issue_type}:{importance}"
    action_id = hashlib.sha256(action_key.encode("utf-8")).hexdigest()[:32]
    severity_weight = SEVERITY_WEIGHT.get(group["severity"], 1)
    business_weight = 1.25 if field_name in QUALITY_FIELD_CANDIDATES else 0.75
    return {
        "id": f"fix_{action_id}",
        "title": title,
        "description": description,
        "actionType": "manual",
        "targetStates": [target_state],
        "recordCount": count,
        "modules": [module_name],
        "fieldApiName": field_name,
        "issueType": issue_type,
        "importance": importance,
        "severity": group["severity"],
        "priority": priority,
        "coverageRate": coverage,
        "pointGain": None,
        "_rank": count * severity_weight * business_weight,
    }


def get_fix_plan(request, datastore, scan_id):
    del datastore
    try:
        zcql = zcatalyst_sdk.initialize().zcql()
        scan_row = find_owned_scan(zcql, scan_id, get_current_user_id(request))
        if not scan_row:
            return json_response(
                {"error": {"code": "SCAN_NOT_FOUND", "message": "Scan was not found"}},
                404,
            )

        selected = _selected_modules(request)
        result_rows = find_analytics_results(zcql, scan_row["ROWID"])
        (
            record_counts,
            measured_modules,
            schema_version,
            aggregate_issue_groups,
        ) = _module_record_counts(result_rows, selected)
        module_rows = find_module_runs(zcql, scan_row["ROWID"])
        module_names = {
            str(row["ROWID"]): str(row.get("module_api_name") or "")
            for row in module_rows
        }

        if not schema_version:
            return json_response(
                {
                    "scanId": scan_id,
                    "measured": False,
                    "measuredModules": [],
                    "actionCount": 0,
                    "omittedActionCount": 0,
                    "actions": [],
                }
            )

        groups = {}
        if schema_version == "record-findings-v3":
            for module_name, module_groups in aggregate_issue_groups.items():
                for aggregate_group in module_groups:
                    field_name = str(aggregate_group.get("fieldApiName") or "")
                    issue_type = str(aggregate_group.get("issueType") or "")
                    importance = str(
                        aggregate_group.get("importance") or "LEGACY"
                    ).upper()
                    if not field_name or not issue_type:
                        continue
                    groups[(module_name, field_name, issue_type, importance)] = {
                        "fieldApiName": field_name,
                        "fieldLabel": str(
                            aggregate_group.get("fieldLabel") or field_name
                        ),
                        "issueType": issue_type,
                        "severity": str(
                            aggregate_group.get("severity") or "LOW"
                        ).upper(),
                        "importance": importance,
                        "recordCount": _integer(aggregate_group.get("recordCount")),
                    }
        else:
            offset = 0
            while True:
                issue_rows = _rows(
                    zcql,
                    "select scan_module_row_id,field_api_name,issue_type,severity,issue_metadata_json "
                    "from record_quality_issues where "
                    f"scan_row_id = {int(scan_row['ROWID'])} and "
                    f"schema_version = '{schema_version}' "
                    f"order by ROWID asc limit {offset},{QUERY_PAGE_SIZE}",
                    "record_quality_issues",
                )
                for issue in issue_rows:
                    module_name = module_names.get(
                        str(foreign_row_id(issue.get("scan_module_row_id")) or ""), ""
                    )
                    if not module_name or (selected and module_name not in selected):
                        continue
                    field_name = str(issue.get("field_api_name") or "")
                    issue_type = str(issue.get("issue_type") or "")
                    severity = str(issue.get("severity") or "LOW").upper()
                    try:
                        metadata = json.loads(issue.get("issue_metadata_json") or "{}")
                    except (TypeError, ValueError, json.JSONDecodeError):
                        metadata = {}
                    importance = str(metadata.get("importance") or "LEGACY").upper()
                    field_label = str(metadata.get("fieldLabel") or field_name)
                    if not field_name or not issue_type:
                        continue
                    key = (module_name, field_name, issue_type, importance)
                    group = groups.setdefault(
                        key,
                        {
                            "fieldApiName": field_name,
                            "fieldLabel": field_label,
                            "issueType": issue_type,
                            "severity": severity,
                            "importance": importance,
                            "recordCount": 0,
                        },
                    )
                    group["recordCount"] += 1
                    if SEVERITY_WEIGHT.get(severity, 1) > SEVERITY_WEIGHT.get(
                        group["severity"], 1
                    ):
                        group["severity"] = severity
                if len(issue_rows) < QUERY_PAGE_SIZE:
                    break
                offset += QUERY_PAGE_SIZE

        actions = [
            _action(group, module_name, record_counts.get(module_name, 0))
            for (module_name, _field, _issue_type, _importance), group in groups.items()
        ]
        actions.sort(
            key=lambda action: (
                {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(action["priority"], 3),
                -action["_rank"],
                action["modules"][0].lower(),
                action["fieldApiName"].lower(),
            )
        )
        total_action_count = len(actions)
        actions = actions[:MAX_ACTIONS]
        for action in actions:
            action.pop("_rank", None)

        return json_response(
            {
                "scanId": scan_id,
                "measured": bool(measured_modules),
                "measuredModules": sorted(measured_modules),
                "actionCount": total_action_count,
                "omittedActionCount": max(0, total_action_count - len(actions)),
                "actions": actions,
            }
        )
    except AuthenticationRequired:
        raise
    except Exception as exc:  # noqa: BLE001 - return a controlled read failure
        LOGGER.exception("Could not build fix plan scan_id=%s: %s", scan_id, exc)
        return json_response(
            {
                "error": {
                    "code": "FIX_PLAN_READ_FAILED",
                    "message": "The remediation plan could not be built",
                }
            },
            500,
        )
