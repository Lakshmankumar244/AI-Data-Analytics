"""Cursor-paginated Fix records: findings index + Stratus JSONL hydration."""

import json
import logging

import zcatalyst_sdk

from analytics.repository import (
    find_analytics_results,
    find_fix_record_findings,
    find_module_runs,
    find_owned_scan,
    find_processing_batches_by_row_ids,
)
from common.core import (
    AuthenticationRequired,
    foreign_row_id,
    get_current_user_id,
    json_response,
    query_list_values,
)
from storage.extract_store import (
    ExtractStorageError,
    build_fix_object_key,
    get_extract,
)


LOGGER = logging.getLogger(__name__)
FIX_SCHEMA_VERSION = "record-findings-v5"
MIN_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50
DEFAULT_PAGE_SIZE = 20
SEARCH_INDEX_PAGE = 50
SIDECAR_ISSUE_FIELDS = (
    "fieldApiName",
    "issueType",
    "severity",
    "messageCode",
    "fieldLabel",
)
ALLOWED_SEVERITIES = frozenset({"LOW", "MEDIUM", "HIGH", "CRITICAL"})


class FixIndexUnavailable(RuntimeError):
    """The v5 findings index or JSONL sidecar is missing or unreadable."""


def _integer(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _sql_string(value):
    return str(value or "").replace("'", "''")


def _safe_tokens(values, max_count=50, max_length=80):
    tokens = []
    seen = set()
    for value in values[:max_count]:
        token = str(value or "").strip()
        if not token or len(token) > max_length:
            continue
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def _issue_type_clause(issue_type):
    token = _sql_string(issue_type)
    return (
        "("
        f"issue_type_keys = '{token}' or "
        f"issue_type_keys like '{token},%' or "
        f"issue_type_keys like '%,{token}' or "
        f"issue_type_keys like '%,{token},%'"
        ")"
    )


def _owner_clause(owners):
    include_unassigned = any(owner == "__unassigned__" for owner in owners)
    owner_keys = [
        _sql_string(owner) for owner in owners if owner != "__unassigned__"
    ]
    clauses = []
    if include_unassigned:
        clauses.append("owner_key = ''")
    if owner_keys:
        clauses.append(
            "owner_key in (" + ",".join(f"'{owner}'" for owner in owner_keys) + ")"
        )
    if not clauses:
        return None
    return "(" + " or ".join(clauses) + ")"


def _page_size(request):
    try:
        size = int(request.args.get("pageSize") or DEFAULT_PAGE_SIZE)
    except (TypeError, ValueError):
        size = DEFAULT_PAGE_SIZE
    return min(max(size, MIN_PAGE_SIZE), MAX_PAGE_SIZE)


def _cursor_row_id(request):
    raw = str(request.args.get("cursor") or "").strip()
    if not raw:
        return None
    if not raw.isdigit():
        raise ValueError("cursor is invalid")
    return raw


def _required_module(request):
    modules = _safe_tokens(query_list_values(request, "module"), max_count=1, max_length=100)
    if len(modules) != 1:
        return None
    return modules[0]


def _error(code, message, status):
    return json_response({"error": {"code": code, "message": message}}, status)


def _module_kpis(result_rows, module_api_name):
    for row in result_rows:
        if (
            row.get("status") != "COMPUTED"
            or row.get("metric_group") != "record_findings"
            or row.get("schema_version") != FIX_SCHEMA_VERSION
            or str(row.get("module_api_name") or "") != module_api_name
        ):
            continue
        try:
            payload = json.loads(row.get("aggregate_json") or "")
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or not payload.get("measured"):
            continue
        return {
            "affectedRecordCount": _integer(payload.get("affectedRecordCount")),
            "issueCount": _integer(payload.get("issueCount")),
        }
    return None


def _module_columns(module_rows, module_api_name):
    module_row = next(
        (
            row
            for row in module_rows
            if str(row.get("module_api_name") or "") == module_api_name
        ),
        None,
    )
    if not module_row:
        return []
    try:
        names = json.loads(module_row.get("field_allowlist_json") or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        names = []
    if not isinstance(names, list):
        names = []
    labels = {}
    try:
        metadata = json.loads(module_row.get("field_metadata_json") or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        metadata = []
    if isinstance(metadata, list):
        for item in metadata:
            if not isinstance(item, dict):
                continue
            api_name = str(item.get("apiName") or "").strip()
            if not api_name:
                continue
            labels[api_name] = str(item.get("label") or api_name)
    columns = []
    for name in names:
        api_name = str(name or "").strip()
        if not api_name:
            continue
        columns.append({"apiName": api_name, "label": labels.get(api_name, api_name)})
    return columns


def _finding_conditions(scan_row, module_api_name, cursor, owners, severities, issue_types):
    conditions = [
        f"scan_row_id = {int(scan_row['ROWID'])}",
        f"module_api_name = '{_sql_string(module_api_name)}'",
        f"schema_version = '{FIX_SCHEMA_VERSION}'",
        "status = 'DETECTED'",
        "issue_count > 0",
    ]
    if cursor:
        conditions.append(f"ROWID > {int(cursor)}")
    owner_clause = _owner_clause(owners)
    if owner_clause:
        conditions.append(owner_clause)
    if severities:
        conditions.append(
            "highest_severity in ("
            + ",".join(f"'{_sql_string(item)}'" for item in severities)
            + ")"
        )
    if issue_types:
        conditions.append(
            "(" + " or ".join(_issue_type_clause(item) for item in issue_types) + ")"
        )
    return conditions


def _normalize_search_value(value):
    return str(value or "").casefold()


def _value_matches_query(value, needle):
    text = _normalize_search_value(value)
    return bool(text) and needle in text


def _row_matches_query(finding, row, needle):
    if not needle:
        return True
    if _value_matches_query(finding.get("display_name"), needle):
        return True
    if _value_matches_query(finding.get("crm_record_id"), needle):
        return True
    if _value_matches_query(finding.get("owner_key"), needle):
        return True
    if _value_matches_query(row.get("displayName"), needle):
        return True
    if _value_matches_query(row.get("crmRecordId"), needle):
        return True
    if _value_matches_query(row.get("ownerKey"), needle):
        return True
    cells = row.get("cells") if isinstance(row.get("cells"), dict) else {}
    return any(_value_matches_query(value, needle) for value in cells.values())


def _jsonl_text(payload):
    if payload is None:
        raise FixIndexUnavailable("Fix sidecar is missing")
    if isinstance(payload, (bytes, bytearray)):
        return payload.decode("utf-8")
    if hasattr(payload, "read") and not isinstance(payload, str):
        data = payload.read()
        if isinstance(data, (bytes, bytearray)):
            return data.decode("utf-8")
        return str(data)
    return str(payload)


def _parse_jsonl(payload):
    lines = []
    for raw in _jsonl_text(payload).splitlines():
        if not raw.strip():
            continue
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise FixIndexUnavailable("Fix sidecar is invalid") from exc
        if not isinstance(parsed, dict):
            raise FixIndexUnavailable("Fix sidecar is invalid")
        lines.append(parsed)
    return lines


def _cells_from_line(line):
    raw_cells = line.get("cells") if isinstance(line, dict) else None
    if not isinstance(raw_cells, dict):
        return {}
    cells = {}
    for key, value in raw_cells.items():
        name = str(key or "").strip()
        if not name:
            continue
        if value is None:
            cells[name] = ""
        else:
            cells[name] = str(value)
    return cells


def _issues_from_line(line):
    raw_issues = line.get("issues") if isinstance(line, dict) else None
    if not isinstance(raw_issues, list):
        return []
    issues = []
    for issue in raw_issues:
        if not isinstance(issue, dict):
            continue
        issues.append(
            {field: str(issue.get(field) or "") for field in SIDECAR_ISSUE_FIELDS}
        )
    return issues


def _load_sidecars(app, scan_id, module_api_name, zcql, findings, sidecars=None):
    sidecars = dict(sidecars or {})
    batch_ids = []
    seen = set(sidecars)
    for finding in findings:
        batch_id = str(foreign_row_id(finding.get("processing_batch_row_id")) or "")
        if not batch_id.isdigit() or batch_id in seen:
            continue
        seen.add(batch_id)
        batch_ids.append(batch_id)
    if not batch_ids:
        if sidecars:
            return sidecars
        raise FixIndexUnavailable("Fix sidecar batch link is missing")

    batch_rows = find_processing_batches_by_row_ids(zcql, batch_ids)
    batches = {
        str(foreign_row_id(row.get("ROWID")) or ""): row for row in batch_rows
    }
    for batch_id in batch_ids:
        batch = batches.get(batch_id)
        if not batch:
            raise FixIndexUnavailable("Fix sidecar batch is missing")
        try:
            key = build_fix_object_key(
                scan_id, module_api_name, batch.get("batch_number")
            )
            payload = get_extract(key, app=app)
        except ExtractStorageError as exc:
            if exc.code in {
                "EXTRACT_NOT_FOUND",
                "EXTRACT_OBJECT_KEY_INVALID",
            }:
                raise FixIndexUnavailable("Fix sidecar is missing") from exc
            raise
        sidecars[batch_id] = _parse_jsonl(payload)
    return sidecars


def _hydrate_rows(findings, sidecars):
    rows = []
    for finding in findings:
        batch_id = str(foreign_row_id(finding.get("processing_batch_row_id")) or "")
        lines = sidecars.get(batch_id)
        if lines is None:
            raise FixIndexUnavailable("Fix sidecar is missing")
        line_index = _integer(finding.get("jsonl_line"))
        if line_index < 0 or line_index >= len(lines):
            raise FixIndexUnavailable("Fix sidecar line is missing")
        line = lines[line_index]
        crm_record_id = str(line.get("crmRecordId") or finding.get("crm_record_id") or "")
        rows.append(
            {
                "crmRecordId": crm_record_id,
                "displayName": str(finding.get("display_name") or ""),
                "ownerKey": str(finding.get("owner_key") or ""),
                "cells": _cells_from_line(line),
                "issues": _issues_from_line(line),
            }
        )
    return rows


def get_fix_records(request, datastore, scan_id):
    del datastore
    try:
        app = zcatalyst_sdk.initialize()
        zcql = app.zcql()
        scan_row = find_owned_scan(zcql, scan_id, get_current_user_id(request))
        if not scan_row:
            return _error("SCAN_NOT_FOUND", "Scan was not found", 404)

        module_api_name = _required_module(request)
        if not module_api_name:
            return _error("MODULE_REQUIRED", "module is required", 400)

        try:
            cursor = _cursor_row_id(request)
        except ValueError:
            return _error("INVALID_CURSOR", "cursor is invalid", 400)

        page_size = _page_size(request)
        owners = _safe_tokens(query_list_values(request, "owner"), max_length=80)
        severities = [
            token.upper()
            for token in _safe_tokens(
                query_list_values(request, "severity"), max_length=40
            )
            if token.upper() in ALLOWED_SEVERITIES
        ]
        issue_types = [
            token.upper()
            for token in _safe_tokens(
                query_list_values(request, "issueType"), max_length=40
            )
        ]
        q = str(request.args.get("q") or "").strip()
        if len(q) > 100:
            q = q[:100]

        result_rows = find_analytics_results(zcql, scan_row["ROWID"])
        kpis = _module_kpis(result_rows, module_api_name)
        if kpis is None:
            raise FixIndexUnavailable("Fix index is unavailable")

        needle = q.casefold()
        matches = []
        scan_cursor = cursor
        sidecars = {}
        fetch_limit = page_size + 1
        if needle:
            fetch_limit = max(page_size + 1, SEARCH_INDEX_PAGE)
        try:
            while len(matches) <= page_size:
                conditions = _finding_conditions(
                    scan_row,
                    module_api_name,
                    scan_cursor,
                    owners,
                    severities,
                    issue_types,
                )
                finding_rows = find_fix_record_findings(zcql, conditions, fetch_limit)
                if not finding_rows:
                    break
                sidecars = _load_sidecars(
                    app,
                    scan_row["scan_id"],
                    module_api_name,
                    zcql,
                    finding_rows,
                    sidecars,
                )
                hydrated = _hydrate_rows(finding_rows, sidecars)
                for finding, row in zip(finding_rows, hydrated):
                    if needle and not _row_matches_query(finding, row, needle):
                        continue
                    matches.append((finding, row))
                    if len(matches) > page_size:
                        break
                if len(matches) > page_size:
                    break
                if len(finding_rows) < fetch_limit:
                    break
                next_scan_cursor = str(finding_rows[-1]["ROWID"])
                if scan_cursor and int(next_scan_cursor) <= int(scan_cursor):
                    break
                scan_cursor = next_scan_cursor
        except (FixIndexUnavailable, ExtractStorageError, AuthenticationRequired):
            raise
        except Exception as exc:  # noqa: BLE001 - missing v5 columns mean no Fix index
            LOGGER.warning("Fix findings index is unreadable scan_id=%s: %s", scan_id, exc)
            raise FixIndexUnavailable("Fix index is unavailable") from exc

        has_more = len(matches) > page_size
        page = matches[:page_size]
        next_cursor = str(page[-1][0]["ROWID"]) if has_more and page else None
        rows = [row for finding_row, row in page]

        columns = _module_columns(
            find_module_runs(zcql, scan_row["ROWID"]), module_api_name
        )
        return json_response(
            {
                "scanId": scan_id,
                "module": module_api_name,
                "measured": True,
                "schemaVersion": FIX_SCHEMA_VERSION,
                "pageSize": page_size,
                "nextCursor": next_cursor,
                "hasMore": has_more,
                "columns": columns,
                "kpis": kpis,
                "rows": rows,
            }
        )
    except FixIndexUnavailable:
        return _error(
            "FIX_INDEX_UNAVAILABLE",
            "Re-run the scan to use Fix",
            409,
        )
    except ExtractStorageError:
        LOGGER.exception("Could not read Fix sidecar scan_id=%s", scan_id)
        return _error(
            "FIX_RECORDS_READ_FAILED",
            "Fix records could not be read",
            500,
        )
    except AuthenticationRequired:
        raise
    except Exception as exc:  # noqa: BLE001 - return a controlled read failure
        LOGGER.exception("Could not read Fix records scan_id=%s: %s", scan_id, exc)
        return _error(
            "FIX_RECORDS_READ_FAILED",
            "Fix records could not be read",
            500,
        )
