"""Authenticated, privacy-safe record finding pagination."""

import json
import logging
from datetime import datetime

import zcatalyst_sdk

from analytics.repository import find_analytics_results, find_owned_scan
from common.core import (
    AuthenticationRequired,
    foreign_row_id,
    get_current_user_id,
    json_response,
    query_list_values,
)


LOGGER = logging.getLogger(__name__)
PAGE_SIZE = 20
MAX_PAGE = 10000
QUERY_BATCH_SIZE = 300
FINDING_IDS_PER_ISSUE_QUERY = 8
SUPPORTED_RECORD_FINDING_SCHEMAS = frozenset(
    {"record-findings-v1", "record-findings-v2", "record-findings-v3"}
)


def _rows(zcql, query, table_name):
    return [item[table_name] for item in zcql.execute_query(query)]


def _all_rows(zcql, query_prefix, table_name):
    rows = []
    offset = 0
    while True:
        page = _rows(
            zcql,
            f"{query_prefix} limit {offset},{QUERY_BATCH_SIZE}",
            table_name,
        )
        rows.extend(page)
        if len(page) < QUERY_BATCH_SIZE:
            return rows
        offset += QUERY_BATCH_SIZE


def _integer(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _utc_timestamp(value):
    timestamp = str(value or "")
    for date_format in ("%Y-%m-%d %H:%M:%S:%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return f"{datetime.strptime(timestamp, date_format).isoformat(timespec='milliseconds')}Z"
        except ValueError:
            continue
    return timestamp


def _safe_values(values, max_count=50, max_length=100):
    safe = []
    for value in values[:max_count]:
        candidate = str(value or "").strip()
        if candidate and len(candidate) <= max_length:
            safe.append(candidate.replace("'", "''"))
    return safe


def _finding_summary(result_rows, selected_modules):
    summary = {
        "measured": False,
        "affectedRecordCount": 0,
        "issueCount": 0,
        "missingIssueCount": 0,
        "invalidIssueCount": 0,
        "staleIssueCount": 0,
        "storedSampleCount": 0,
        "sampleLimit": 0,
        "schemaVersion": None,
    }
    selected = set(selected_modules)
    candidates = []
    for row in result_rows:
        if (
            row.get("status") != "COMPUTED"
            or row.get("metric_group") != "record_findings"
            or row.get("schema_version") not in SUPPORTED_RECORD_FINDING_SCHEMAS
            or (selected and row.get("module_api_name") not in selected)
        ):
            continue
        try:
            payload = json.loads(row.get("aggregate_json") or "")
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or not payload.get("measured"):
            continue
        candidates.append((row, payload))

    if not candidates:
        return summary
    preferred_schema = max(str(row.get("schema_version") or "") for row, _ in candidates)
    summary["schemaVersion"] = preferred_schema
    for row, payload in candidates:
        if row.get("schema_version") != preferred_schema:
            continue
        summary["measured"] = True
        for key in (
            "affectedRecordCount",
            "issueCount",
            "missingIssueCount",
            "invalidIssueCount",
            "staleIssueCount",
            "storedSampleCount",
            "sampleLimit",
        ):
            summary[key] += _integer(payload.get(key))
    return summary


def _owner_names(zcql, scan_row):
    connection_row_id = str(foreign_row_id(scan_row.get("connection_row_id")) or "")
    if not connection_row_id.isdigit():
        return {}
    try:
        rows = _rows(
            zcql,
            "select crm_user_key,display_name from zoho_connection_users where "
            f"connection_row_id = {connection_row_id} and status = 'ACTIVE'",
            "zoho_connection_users",
        )
    except Exception as exc:  # noqa: BLE001 - names are optional presentation metadata
        LOGGER.warning("Could not read owner names for record findings: %s", exc)
        return {}
    return {
        str(row.get("crm_user_key") or ""): str(
            row.get("display_name") or "Unknown owner"
        )
        for row in rows
        if row.get("crm_user_key")
    }


def _reason(finding):
    parts = []
    missing = _integer(finding.get("missing_count"))
    invalid = _integer(finding.get("invalid_count"))
    stale = _integer(finding.get("stale_count"))
    if missing:
        parts.append(f"{missing} missing field{'s' if missing != 1 else ''}")
    if invalid:
        parts.append(f"{invalid} invalid value{'s' if invalid != 1 else ''}")
    if stale:
        parts.append(f"{stale} freshness issue{'s' if stale != 1 else ''}")
    return "; ".join(parts) or "Quality issue detected"


def get_record_findings(request, datastore, scan_id):
    del datastore
    try:
        zcql = zcatalyst_sdk.initialize().zcql()
        scan_row = find_owned_scan(zcql, scan_id, get_current_user_id(request))
        if not scan_row:
            return json_response(
                {"error": {"code": "SCAN_NOT_FOUND", "message": "Scan was not found"}},
                404,
            )

        try:
            page = int(request.args.get("page", "1"))
        except (TypeError, ValueError):
            page = 1
        page = min(max(page, 1), MAX_PAGE)
        modules = _safe_values(query_list_values(request, "module"))
        states = set(
            _safe_values(
                query_list_values(request, "state"),
                max_length=40,
            )
        )
        supported_states = states & {"incomplete", "inaccurate"}
        summary = _finding_summary(
            find_analytics_results(zcql, scan_row["ROWID"]), modules
        )
        if states and not supported_states:
            return json_response(
                {
                    "scanId": scan_id,
                    "page": page,
                    "pageSize": PAGE_SIZE,
                    "hasMore": False,
                    "summary": summary,
                    "records": [],
                }
            )

        schema_version = summary.get("schemaVersion")
        if not summary["measured"] or not schema_version:
            return json_response(
                {
                    "scanId": scan_id,
                    "page": page,
                    "pageSize": PAGE_SIZE,
                    "hasMore": False,
                    "summary": summary,
                    "records": [],
                }
            )

        conditions = [
            f"scan_row_id = {int(scan_row['ROWID'])}",
            f"schema_version = '{schema_version}'",
            "status = 'DETECTED'",
        ]
        if modules:
            conditions.append(
                "module_api_name in ("
                + ",".join(f"'{module}'" for module in modules)
                + ")"
            )
        state_conditions = []
        if "incomplete" in supported_states:
            state_conditions.append("(missing_count > 0 and invalid_count = 0)")
        if "inaccurate" in supported_states:
            state_conditions.append("invalid_count > 0")
        if state_conditions:
            conditions.append("(" + " or ".join(state_conditions) + ")")

        offset = (page - 1) * PAGE_SIZE
        finding_rows = _rows(
            zcql,
            "select ROWID,finding_id,record_key,owner_key,module_api_name,"
            "issue_count,missing_count,invalid_count,stale_count,"
            "highest_severity,computed_at from record_quality_findings where "
            + " and ".join(conditions)
            + f" order by ROWID asc limit {offset},{PAGE_SIZE + 1}",
            "record_quality_findings",
        )
        has_more = len(finding_rows) > PAGE_SIZE
        finding_rows = finding_rows[:PAGE_SIZE]

        issues_by_finding = {}
        finding_row_ids = [str(row["ROWID"]) for row in finding_rows]
        for start in range(0, len(finding_row_ids), FINDING_IDS_PER_ISSUE_QUERY):
            issue_rows = _all_rows(
                zcql,
                "select * from record_quality_issues where ("
                + " or ".join(
                    f"finding_row_id = {row_id}"
                    for row_id in finding_row_ids[
                        start : start + FINDING_IDS_PER_ISSUE_QUERY
                    ]
                )
                + ") order by ROWID asc",
                "record_quality_issues",
            )
            for issue in issue_rows:
                finding_row_id = str(
                    foreign_row_id(issue.get("finding_row_id")) or ""
                )
                try:
                    metadata = json.loads(issue.get("issue_metadata_json") or "{}")
                except (TypeError, ValueError, json.JSONDecodeError):
                    metadata = {}
                issues_by_finding.setdefault(finding_row_id, []).append(
                    {
                        "fieldApiName": issue.get("field_api_name"),
                        "metricGroup": issue.get("metric_group"),
                        "issueType": issue.get("issue_type"),
                        "severity": issue.get("severity"),
                        "messageCode": metadata.get("messageCode"),
                        "importance": metadata.get("importance"),
                        "fieldLabel": metadata.get("fieldLabel")
                        or issue.get("field_api_name"),
                    }
                )

        owner_names = _owner_names(zcql, scan_row)
        records = []
        for finding in finding_rows:
            invalid_count = _integer(finding.get("invalid_count"))
            record_key = str(finding.get("record_key") or "")
            owner_key = str(finding.get("owner_key") or "")
            records.append(
                {
                    "findingId": finding.get("finding_id"),
                    "recordRef": f"{finding.get('module_api_name')} - {record_key[:12]}",
                    "module": finding.get("module_api_name"),
                    "state": "inaccurate" if invalid_count else "incomplete",
                    "severity": str(finding.get("highest_severity") or "LOW").lower(),
                    "reason": _reason(finding),
                    "ownerName": owner_names.get(owner_key, "Unassigned" if not owner_key else "Unknown owner"),
                    "issueCount": _integer(finding.get("issue_count")),
                    "issues": issues_by_finding.get(str(finding["ROWID"]), []),
                    "computedAt": _utc_timestamp(finding.get("computed_at")),
                }
            )

        return json_response(
            {
                "scanId": scan_id,
                "page": page,
                "pageSize": PAGE_SIZE,
                "hasMore": has_more,
                "summary": summary,
                "records": records,
            }
        )
    except AuthenticationRequired:
        raise
    except Exception as exc:  # noqa: BLE001 - return a controlled read failure
        LOGGER.exception("Could not read record findings scan_id=%s: %s", scan_id, exc)
        return json_response(
            {
                "error": {
                    "code": "RECORD_FINDINGS_READ_FAILED",
                    "message": "Record findings could not be read",
                }
            },
            500,
        )
