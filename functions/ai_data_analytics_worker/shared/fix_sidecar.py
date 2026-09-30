"""Defective-record JSONL sidecars written during PROCESS_BATCHES.

Each line is one CRM record that has at least one quality issue. Clean records
are omitted. Cell values are the actual allowlisted CRM values from the extract
already in worker memory — this module does not download the extract.
"""

from __future__ import annotations

import json

from storage.extract_store import build_fix_object_key, put_extract


SIDECAR_ISSUE_FIELDS = (
    "fieldApiName",
    "issueType",
    "severity",
    "messageCode",
    "fieldLabel",
)


def compact_issue_type_keys(issues):
    """Stable comma-separated unique issue types for the findings index."""
    seen = set()
    keys = []
    for issue in issues or []:
        issue_type = str((issue or {}).get("issueType") or "").strip()
        if not issue_type or issue_type in seen:
            continue
        seen.add(issue_type)
        keys.append(issue_type)
    keys.sort()
    return ",".join(keys)


def cells_from_fields(fields):
    """Map allowlisted field API names to their raw CRM string values."""
    cells = {}
    for name, evaluated in (fields or {}).items():
        if isinstance(evaluated, dict):
            value = evaluated.get("value")
            cells[str(name)] = "" if value is None else str(value)
        elif evaluated is None:
            cells[str(name)] = ""
        else:
            cells[str(name)] = str(evaluated)
    return cells


def issues_payload(issues):
    """Field-level defect metadata without duplicating the cell value."""
    payload = []
    for issue in issues or []:
        if not isinstance(issue, dict):
            continue
        payload.append(
            {field: str(issue.get(field) or "") for field in SIDECAR_ISSUE_FIELDS}
        )
    return payload


def build_sidecar_line(crm_record_id, fields, issues):
    return {
        "crmRecordId": str(crm_record_id or ""),
        "cells": cells_from_fields(fields),
        "issues": issues_payload(issues),
    }


def attach_sidecar_line(finding, fields, jsonl_lines):
    """Stamp jsonl_line / issue_type_keys on a finding and append a JSONL line."""
    line_index = len(jsonl_lines)
    finding["jsonlLine"] = line_index
    finding["issueTypeKeys"] = compact_issue_type_keys(finding.get("issues"))
    jsonl_lines.append(
        build_sidecar_line(
            finding.get("crmRecordId"),
            fields,
            finding.get("issues"),
        )
    )
    return finding


def encode_fix_jsonl(lines):
    chunks = []
    for line in lines or []:
        chunks.append(
            json.dumps(line, ensure_ascii=True, separators=(",", ":"))
        )
        chunks.append("\n")
    return "".join(chunks).encode("utf-8")


def write_fix_sidecar(app, scan_id, module_api_name, batch_number, lines):
    """Overwrite the batch sidecar on Stratus. Empty batches still get an object."""
    key = build_fix_object_key(scan_id, module_api_name, batch_number)
    put_extract(key, encode_fix_jsonl(lines), app=app)
    return key
