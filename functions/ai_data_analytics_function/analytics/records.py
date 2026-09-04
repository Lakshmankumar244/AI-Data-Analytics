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
    {"record-findings-v1", "record-findings-v2", "record-findings-v3", "record-findings-v4"}
)
LISTABLE_STATES = ("incomplete", "inaccurate")
UNNAMED_RECORD = "Unnamed record"


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


def _record_search_text(record):
    parts = [
        record.get("recordName"),
        record.get("recordRef"),
        record.get("module"),
        record.get("reason"),
        record.get("ownerName"),
    ]
    for issue in record.get("issues") or []:
        parts.append(issue.get("fieldLabel"))
        parts.append(issue.get("fieldApiName"))
    return " ".join(str(part or "") for part in parts).casefold()


def _empty_listed_states():
    return {
        "proper": 0,
        "incomplete": 0,
        "inaccurate": 0,
        "suspicious": 0,
        "suspected_duplicate": 0,
        "confirmed_duplicate": 0,
        "listedRecordCount": 0,
    }


def _finding_scope_conditions(scan_row, schema_version, modules, owners):
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
    include_unassigned = any(owner == "__unassigned__" for owner in owners)
    owner_keys = [owner for owner in owners if owner != "__unassigned__"]
    owner_conditions = []
    if include_unassigned:
        owner_conditions.append("owner_key = ''")
    if owner_keys:
        owner_conditions.append(
            "owner_key in ("
            + ",".join(f"'{owner}'" for owner in owner_keys)
            + ")"
        )
    if owner_conditions:
        conditions.append("(" + " or ".join(owner_conditions) + ")")
    return conditions


def _listed_state_counts(zcql, conditions):
    counts = _empty_listed_states()
    rows = _all_rows(
        zcql,
        "select missing_count,invalid_count from record_quality_findings where "
        + " and ".join(conditions),
        "record_quality_findings",
    )
    for row in rows:
        if _integer(row.get("invalid_count")) > 0:
            counts["inaccurate"] += 1
        elif _integer(row.get("missing_count")) > 0:
            counts["incomplete"] += 1
    counts["listedRecordCount"] = counts["incomplete"] + counts["inaccurate"]
    return counts


def _records_payload(scan_id, page, summary, records, has_more=False):
    return {
        "scanId": scan_id,
        "page": page,
        "pageSize": PAGE_SIZE,
        "hasMore": has_more,
        "summary": summary,
        "records": records,
    }


def _connection_row(zcql, scan_row):
    connection_id = str(foreign_row_id(scan_row.get("connection_row_id")) or "")
    if not connection_id.isdigit():
        return None
    rows = _rows(
        zcql,
        f"select * from zoho_connections where ROWID = {connection_id} limit 1",
        "zoho_connections",
    )
    return rows[0] if rows else None


def _safe_crm_record_id(value):
    candidate = str(value or "").strip()
    return candidate if candidate.isdigit() and len(candidate) <= 32 else ""


def _is_module_name(value, module_api_name):
    candidate = str(value or "").strip().casefold()
    module = str(module_api_name or "").strip().casefold()
    return bool(candidate) and candidate == module


def _enrich_record_names(datastore, zcql, scan_row, records):
    for record in records:
        name = str(record.get("recordName") or "").strip()
        if name and not _is_module_name(name, record.get("module")):
            record["recordName"] = name
            record["recordRef"] = name
            continue
        record["recordName"] = None
        record["recordRef"] = UNNAMED_RECORD

    missing = [
        record
        for record in records
        if not record.get("recordName") and record.get("crmRecordId")
    ]
    if not missing:
        for record in records:
            record.pop("crmRecordId", None)
        return records

    connection = _connection_row(zcql, scan_row)
    if not connection:
        for record in records:
            record.pop("crmRecordId", None)
        return records

    try:
        from connections.routes import get_connection_access_token
        from zoho.client import fetch_record_names

        access_token, api_domain, _refreshed = get_connection_access_token(
            datastore, connection
        )
    except Exception as exc:  # noqa: BLE001 - names are optional presentation data
        LOGGER.warning("Could not resolve CRM record names: %s", exc)
        for record in records:
            record.pop("crmRecordId", None)
        return records

    by_module = {}
    for record in missing:
        by_module.setdefault(record.get("module") or "", []).append(record)
    for module_api_name, module_records in by_module.items():
        try:
            names = fetch_record_names(
                access_token,
                api_domain,
                module_api_name,
                [record["crmRecordId"] for record in module_records],
            )
        except Exception as exc:  # noqa: BLE001 - keep the finding list if CRM lookup fails
            LOGGER.warning(
                "Could not read record names for module %s: %s",
                module_api_name,
                exc,
            )
            names = {}
        for record in module_records:
            name = str(names.get(record["crmRecordId"]) or "").strip()
            if name and not _is_module_name(name, module_api_name):
                record["recordName"] = name
                record["recordRef"] = name

    for record in records:
        record.pop("crmRecordId", None)
    return records


def get_record_findings(request, datastore, scan_id):
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
        owners = _safe_values(
            query_list_values(request, "owner"),
            max_count=50,
            max_length=80,
        )
        states = set(
            _safe_values(
                query_list_values(request, "state"),
                max_length=40,
            )
        )
        supported_states = states & set(LISTABLE_STATES)
        summary = _finding_summary(
            find_analytics_results(zcql, scan_row["ROWID"]), modules
        )
        summary["stateCounts"] = _empty_listed_states()

        schema_version = summary.get("schemaVersion")
        if not summary["measured"] or not schema_version:
            return json_response(
                _records_payload(scan_id, page, summary, []),
            )

        scope_conditions = _finding_scope_conditions(
            scan_row, schema_version, modules, owners
        )
        summary["stateCounts"] = _listed_state_counts(zcql, scope_conditions)
        if states and not supported_states:
            return json_response(
                _records_payload(scan_id, page, summary, []),
            )

        conditions = list(scope_conditions)
        state_conditions = []
        if "incomplete" in supported_states:
            state_conditions.append("(missing_count > 0 and invalid_count = 0)")
        if "inaccurate" in supported_states:
            state_conditions.append("invalid_count > 0")
        if state_conditions:
            conditions.append("(" + " or ".join(state_conditions) + ")")

        search = str(request.args.get("q") or "").strip()
        offset = 0 if search else (page - 1) * PAGE_SIZE
        fetch_limit = 301 if search else PAGE_SIZE + 1
        finding_query_suffix = (
            " from record_quality_findings where "
            + " and ".join(conditions)
            + f" order by ROWID asc limit {offset},{fetch_limit}"
        )
        try:
            finding_rows = _rows(
                zcql,
                "select ROWID,finding_id,record_key,crm_record_id,owner_key,"
                "module_api_name,issue_count,missing_count,invalid_count,"
                "stale_count,highest_severity,computed_at"
                + finding_query_suffix,
                "record_quality_findings",
            )
        except Exception:  # noqa: BLE001 - older tables may omit crm_record_id
            LOGGER.warning("Record findings query without crm_record_id fallback")
            finding_rows = _rows(
                zcql,
                "select ROWID,finding_id,record_key,owner_key,module_api_name,"
                "issue_count,missing_count,invalid_count,stale_count,"
                "highest_severity,computed_at"
                + finding_query_suffix,
                "record_quality_findings",
            )
        has_more = len(finding_rows) > PAGE_SIZE
        if not search:
            finding_rows = finding_rows[:PAGE_SIZE]

        issues_by_finding = {}
        finding_row_ids = [str(row["ROWID"]) for row in finding_rows]
        if finding_row_ids:
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
                            "recordDisplayName": metadata.get("recordDisplayName") or "",
                        }
                    )

        owner_names = _owner_names(zcql, scan_row)
        records = []
        for finding in finding_rows:
            invalid_count = _integer(finding.get("invalid_count"))
            owner_key = str(finding.get("owner_key") or "")
            issues = issues_by_finding.get(str(finding["ROWID"]), [])
            display_name = next(
                (
                    str(issue.get("recordDisplayName") or "").strip()
                    for issue in issues
                    if issue.get("recordDisplayName")
                    and not _is_module_name(
                        issue.get("recordDisplayName"),
                        finding.get("module_api_name"),
                    )
                ),
                "",
            )
            records.append(
                {
                    "findingId": finding.get("finding_id"),
                    "recordName": display_name or None,
                    "recordRef": display_name or UNNAMED_RECORD,
                    "crmRecordId": _safe_crm_record_id(finding.get("crm_record_id")),
                    "module": finding.get("module_api_name"),
                    "state": "inaccurate" if invalid_count else "incomplete",
                    "severity": str(finding.get("highest_severity") or "LOW").lower(),
                    "reason": _reason(finding),
                    "ownerName": owner_names.get(owner_key, "Unassigned" if not owner_key else "Unknown owner"),
                    "issueCount": _integer(finding.get("issue_count")),
                    "issues": issues,
                    "computedAt": _utc_timestamp(finding.get("computed_at")),
                }
            )

        records = _enrich_record_names(datastore, zcql, scan_row, records)
        if search:
            needle = search.casefold()
            records = [
                record for record in records if needle in _record_search_text(record)
            ]
            start = (page - 1) * PAGE_SIZE
            has_more = len(records) > start + PAGE_SIZE
            records = records[start : start + PAGE_SIZE]

        return json_response(
            _records_payload(scan_id, page, summary, records, has_more)
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
