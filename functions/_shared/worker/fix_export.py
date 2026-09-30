"""Cursor through filtered Fix findings and write a private Stratus XLSX.

The HTTP function must not import this module. Job Functions cursor the v5
findings index, hydrate JSONL sidecars one processing batch at a time, and
write with xlsxwriter constant_memory so the complete result set is never
held as rows.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile

from shared.datastore import foreign_row_id, query_one
from storage.extract_store import (
    ExtractStorageError,
    build_fix_export_object_key,
    build_fix_object_key,
    get_extract,
    put_extract,
)


LOGGER = logging.getLogger(__name__)
EXPORT_TASK_TYPE = "EXPORT_FIX_XLSX"
FIX_SCHEMA_VERSION = "record-findings-v5"
FINDING_PAGE_SIZE = 300
XLSX_WORKBOOK_OPTIONS = {"constant_memory": True, "in_memory": False}
DEFECT_FILL_COLOR = "#FBEAE8"
DEFECT_FONT_COLOR = "#7A1F16"
SIDECAR_ISSUE_FIELDS = (
    "fieldApiName",
    "issueType",
    "severity",
    "messageCode",
    "fieldLabel",
)
ISSUE_TYPE_MESSAGES = {
    "MISSING_VALUE": "Missing value",
    "INVALID_EMAIL": "Invalid email",
    "INVALID_PHONE": "Invalid phone",
    "INVALID_URL": "Invalid URL",
    "INVALID_NUMBER": "Invalid number",
    "INVALID_DATETIME": "Invalid date/time",
}
MESSAGE_CODE_MESSAGES = {
    "INVALID_EMAIL_FORMAT": "Invalid email",
    "INVALID_PHONE_FORMAT": "Invalid phone",
    "INVALID_URL_FORMAT": "Invalid URL",
    "INVALID_NUMBER_FORMAT": "Invalid number",
    "INVALID_DATETIME_FORMAT": "Invalid date/time",
    "SYSTEM_MANDATORY_VALUE_MISSING": "Missing value",
    "UNIQUE_FIELD_VALUE_MISSING": "Missing value",
    "BUSINESS_CRITICAL_VALUE_MISSING": "Missing value",
    "OPTIONAL_VALUE_MISSING": "Missing value",
    "LEGACY_ANALYSIS_VALUE_MISSING": "Missing value",
}


class FixExportError(RuntimeError):
    """Controlled Fix export failure."""

    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def export_fix_xlsx(app, task_row):
    """Write the filtered Fix workbook and persist result_file_key."""
    zcql = app.zcql()
    request = _request_from_task(task_row)
    scan_row = _scan_row(zcql, task_row)
    scan_id = str(scan_row.get("scan_id") or "")
    export_id = str(task_row.get("task_id") or "").strip()
    if not scan_id or not export_id:
        raise FixExportError("FIX_EXPORT_INVALID", "Fix export identifiers are missing")

    module_api_name = request["module"]
    columns = _module_columns(zcql, scan_row, module_api_name)
    object_key = build_fix_export_object_key(scan_id, export_id)

    xlsx_path = None
    defects_path = None
    try:
        xlsx_handle = tempfile.NamedTemporaryFile(prefix="ada_fix_", suffix=".xlsx", delete=False)
        xlsx_handle.close()
        xlsx_path = xlsx_handle.name
        defects_handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix="ada_fix_defects_",
            suffix=".jsonl",
            delete=False,
        )
        defects_path = defects_handle.name

        workbook = _open_workbook(xlsx_path)
        records_sheet = workbook.add_worksheet("Records")
        defect_format = workbook.add_format(
            {
                "bg_color": DEFECT_FILL_COLOR,
                "font_color": DEFECT_FONT_COLOR,
            }
        )
        header_format = workbook.add_format({"bold": True})
        _write_records_header(records_sheet, columns, header_format)

        record_count = 0
        issue_count = 0
        cursor = None
        record_row = 1
        try:
            while True:
                findings = _page_findings(
                    zcql, scan_row, request, cursor, FINDING_PAGE_SIZE
                )
                if not findings:
                    break
                sidecars = _load_sidecars(app, scan_id, module_api_name, zcql, findings)
                for finding in findings:
                    record = _hydrate_finding(finding, sidecars)
                    _write_record_row(
                        records_sheet,
                        record_row,
                        record,
                        columns,
                        defect_format,
                    )
                    record_row += 1
                    record_count += 1
                    for issue in record["issues"]:
                        defects_handle.write(
                            json.dumps(
                                {
                                    "crmRecordId": record["crmRecordId"],
                                    "field": issue.get("fieldLabel") or issue.get("fieldApiName"),
                                    "issueType": issue.get("issueType") or "",
                                    "severity": issue.get("severity") or "",
                                    "message": _issue_message(issue),
                                    "actualValue": record["cells"].get(
                                        issue.get("fieldApiName"), ""
                                    ),
                                },
                                ensure_ascii=True,
                                separators=(",", ":"),
                            )
                        )
                        defects_handle.write("\n")
                        issue_count += 1
                cursor = str(findings[-1].get("ROWID") or "")
                if not cursor.isdigit():
                    raise FixExportError("FIX_EXPORT_INVALID", "Fix finding cursor is invalid")
                if len(findings) < FINDING_PAGE_SIZE:
                    break
        finally:
            defects_handle.close()

        defects_sheet = workbook.add_worksheet("Defects")
        _write_defects_sheet(defects_sheet, defects_path, header_format)
        workbook.close()

        with open(xlsx_path, "rb") as handle:
            body = handle.read()
        put_extract(object_key, body, app=app)
    finally:
        if xlsx_path and os.path.exists(xlsx_path):
            os.remove(xlsx_path)
        if defects_path and os.path.exists(defects_path):
            os.remove(defects_path)

    _persist_result_file_key(app, task_row, object_key)
    LOGGER.info(
        "FIX_EXPORT_WRITTEN taskId=%s scanId=%s objectKey=%s records=%s issues=%s",
        export_id,
        scan_id,
        object_key,
        record_count,
        issue_count,
    )
    return {
        "outcome": "SUCCEEDED",
        "taskId": export_id,
        "scanId": scan_id,
        "objectKey": object_key,
        "recordCount": record_count,
        "issueCount": issue_count,
    }


def _open_workbook(path):
    try:
        import xlsxwriter
    except ImportError as exc:
        raise FixExportError(
            "FIX_EXPORT_WRITER_MISSING",
            "xlsxwriter is required in the Job Function",
        ) from exc
    return xlsxwriter.Workbook(path, dict(XLSX_WORKBOOK_OPTIONS))


def _request_from_task(task_row):
    raw = (task_row or {}).get("request_json")
    if isinstance(raw, dict):
        payload = raw
    else:
        text = str(raw or "").strip()
        if not text:
            raise FixExportError("FIX_EXPORT_INVALID", "Fix export request is missing")
        try:
            payload = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise FixExportError("FIX_EXPORT_INVALID", "Fix export request is invalid") from exc
    module = str((payload or {}).get("module") or "").strip()
    if not module:
        raise FixExportError("MODULE_REQUIRED", "module is required")
    owners = payload.get("owners") if isinstance(payload.get("owners"), list) else []
    return {
        "module": module,
        "q": str((payload or {}).get("q") or "").strip()[:100],
        "owners": [str(item).strip() for item in owners if str(item).strip()],
        "severity": str((payload or {}).get("severity") or "").strip().upper(),
        "issueType": str((payload or {}).get("issueType") or "").strip().upper(),
    }


def _scan_row(zcql, task_row):
    scan_row_id = str(foreign_row_id((task_row or {}).get("scan_row_id")) or "")
    if not scan_row_id.isdigit():
        raise FixExportError("SCAN_NOT_FOUND", "Scan was not found")
    row = query_one(
        zcql,
        f"select * from scan_jobs where ROWID = {scan_row_id} limit 1",
        "scan_jobs",
    )
    if not row:
        raise FixExportError("SCAN_NOT_FOUND", "Scan was not found")
    return row


def _sql_string(value):
    return str(value or "").replace("'", "''")


def _like_prefix(value):
    return _sql_string(value).replace("%", "").replace("_", "")


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
    owner_keys = [_sql_string(owner) for owner in owners if owner != "__unassigned__"]
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


def _finding_conditions(scan_row, request, cursor):
    conditions = [
        f"scan_row_id = {int(scan_row['ROWID'])}",
        f"module_api_name = '{_sql_string(request['module'])}'",
        f"schema_version = '{FIX_SCHEMA_VERSION}'",
        "status = 'DETECTED'",
        "issue_count > 0",
    ]
    if cursor:
        conditions.append(f"ROWID > {int(cursor)}")
    owner_clause = _owner_clause(request.get("owners") or [])
    if owner_clause:
        conditions.append(owner_clause)
    severity = str(request.get("severity") or "").strip().upper()
    if severity:
        conditions.append(f"highest_severity = '{_sql_string(severity)}'")
    issue_type = str(request.get("issueType") or "").strip().upper()
    if issue_type:
        conditions.append(_issue_type_clause(issue_type))
    needle = str(request.get("q") or "").strip()
    if needle:
        exact = _sql_string(needle)
        prefix = _like_prefix(needle)
        search_clauses = [f"crm_record_id = '{exact}'"]
        if prefix:
            search_clauses.append(f"display_name = '{exact}'")
            search_clauses.append(f"display_name like '{prefix}%'")
        conditions.append("(" + " or ".join(search_clauses) + ")")
    return conditions


def _page_findings(zcql, scan_row, request, cursor, fetch_limit):
    conditions = _finding_conditions(scan_row, request, cursor)
    limit = int(fetch_limit)
    results = zcql.execute_query(
        "select ROWID,crm_record_id,display_name,owner_key,highest_severity,"
        "processing_batch_row_id,jsonl_line,issue_type_keys,module_api_name,"
        "schema_version,issue_count from record_quality_findings where "
        + " and ".join(conditions)
        + f" order by ROWID asc limit 0,{limit}"
    )
    return [item["record_quality_findings"] for item in results]


def _module_columns(zcql, scan_row, module_api_name):
    results = zcql.execute_query(
        "select * from scan_module_runs where "
        f"scan_row_id = {int(scan_row['ROWID'])}"
    )
    module_row = next(
        (
            item["scan_module_runs"]
            for item in results
            if str(item["scan_module_runs"].get("module_api_name") or "") == module_api_name
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


def _jsonl_text(payload):
    if payload is None:
        raise FixExportError("FIX_INDEX_UNAVAILABLE", "Fix sidecar is missing")
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
            raise FixExportError("FIX_INDEX_UNAVAILABLE", "Fix sidecar is invalid") from exc
        if not isinstance(parsed, dict):
            raise FixExportError("FIX_INDEX_UNAVAILABLE", "Fix sidecar is invalid")
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
        cells[name] = "" if value is None else str(value)
    return cells


def _issues_from_line(line):
    raw_issues = line.get("issues") if isinstance(line, dict) else None
    if not isinstance(raw_issues, list):
        return []
    issues = []
    for issue in raw_issues:
        if not isinstance(issue, dict):
            continue
        issues.append({field: str(issue.get(field) or "") for field in SIDECAR_ISSUE_FIELDS})
    return issues


def _load_sidecars(app, scan_id, module_api_name, zcql, findings):
    batch_ids = []
    seen = set()
    for finding in findings:
        batch_id = str(foreign_row_id(finding.get("processing_batch_row_id")) or "")
        if not batch_id.isdigit() or batch_id in seen:
            continue
        seen.add(batch_id)
        batch_ids.append(batch_id)
    if not batch_ids:
        raise FixExportError("FIX_INDEX_UNAVAILABLE", "Fix sidecar batch link is missing")

    results = zcql.execute_query(
        "select ROWID,batch_number from processing_batches where "
        f"ROWID in ({','.join(batch_ids)})"
    )
    batches = {
        str(foreign_row_id(item["processing_batches"].get("ROWID")) or ""): item[
            "processing_batches"
        ]
        for item in results
    }
    sidecars = {}
    for batch_id in batch_ids:
        batch = batches.get(batch_id)
        if not batch:
            raise FixExportError("FIX_INDEX_UNAVAILABLE", "Fix sidecar batch is missing")
        try:
            key = build_fix_object_key(scan_id, module_api_name, batch.get("batch_number"))
            payload = get_extract(key, app=app)
        except ExtractStorageError as exc:
            if exc.code in {"EXTRACT_NOT_FOUND", "EXTRACT_OBJECT_KEY_INVALID"}:
                raise FixExportError("FIX_INDEX_UNAVAILABLE", "Fix sidecar is missing") from exc
            raise
        sidecars[batch_id] = _parse_jsonl(payload)
    return sidecars


def _hydrate_finding(finding, sidecars):
    batch_id = str(foreign_row_id(finding.get("processing_batch_row_id")) or "")
    lines = sidecars.get(batch_id)
    if lines is None:
        raise FixExportError("FIX_INDEX_UNAVAILABLE", "Fix sidecar is missing")
    try:
        line_index = int(finding.get("jsonl_line") or 0)
    except (TypeError, ValueError):
        line_index = -1
    if line_index < 0 or line_index >= len(lines):
        raise FixExportError("FIX_INDEX_UNAVAILABLE", "Fix sidecar line is missing")
    line = lines[line_index]
    return {
        "crmRecordId": str(line.get("crmRecordId") or finding.get("crm_record_id") or ""),
        "displayName": str(finding.get("display_name") or ""),
        "cells": _cells_from_line(line),
        "issues": _issues_from_line(line),
    }


def _issue_message(issue):
    code = str((issue or {}).get("messageCode") or "").strip()
    if MESSAGE_CODE_MESSAGES.get(code):
        return MESSAGE_CODE_MESSAGES[code]
    issue_type = str((issue or {}).get("issueType") or "").strip()
    if ISSUE_TYPE_MESSAGES.get(issue_type):
        return ISSUE_TYPE_MESSAGES[issue_type]
    label = str((issue or {}).get("fieldLabel") or (issue or {}).get("fieldApiName") or "").strip()
    if issue_type:
        readable = issue_type.replace("_", " ").lower()
        return f"{readable} · {label}" if label else issue_type
    return "Quality issue detected"


def _write_records_header(sheet, columns, header_format):
    sheet.write(0, 0, "Record ID", header_format)
    sheet.write(0, 1, "Record name", header_format)
    for index, column in enumerate(columns, start=2):
        sheet.write(0, index, column["label"], header_format)


def _write_record_row(sheet, row_index, record, columns, defect_format):
    defective = {
        str(issue.get("fieldApiName") or "").strip()
        for issue in record.get("issues") or []
        if str(issue.get("fieldApiName") or "").strip()
    }
    sheet.write(row_index, 0, record.get("crmRecordId") or "")
    sheet.write(row_index, 1, record.get("displayName") or "")
    cells = record.get("cells") or {}
    for index, column in enumerate(columns, start=2):
        api_name = column["apiName"]
        value = cells.get(api_name, "")
        if api_name in defective:
            sheet.write(row_index, index, value, defect_format)
        else:
            sheet.write(row_index, index, value)


def _write_defects_sheet(sheet, defects_path, header_format):
    headers = (
        "Record ID",
        "Field",
        "Issue type",
        "Severity",
        "Message",
        "Actual value",
    )
    for index, header in enumerate(headers):
        sheet.write(0, index, header, header_format)
    row_index = 1
    with open(defects_path, encoding="utf-8") as handle:
        for raw in handle:
            if not raw.strip():
                continue
            row = json.loads(raw)
            sheet.write(row_index, 0, str(row.get("crmRecordId") or ""))
            sheet.write(row_index, 1, str(row.get("field") or ""))
            sheet.write(row_index, 2, str(row.get("issueType") or ""))
            sheet.write(row_index, 3, str(row.get("severity") or ""))
            sheet.write(row_index, 4, str(row.get("message") or ""))
            sheet.write(row_index, 5, str(row.get("actualValue") or ""))
            row_index += 1


def _persist_result_file_key(app, task_row, object_key):
    app.datastore().table("pipeline_tasks").update_row(
        {
            "ROWID": task_row["ROWID"],
            "result_file_key": object_key,
        }
    )
    task_row["result_file_key"] = object_key
