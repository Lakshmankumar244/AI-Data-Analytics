"""Read clean CRM records from the stored Bulk Read export for a scan.

Clean rows are not persisted as findings. The scan already stored the export
CSV and the same field plan used during processing; this module reapplies
those completeness/validity rules at read time without changing stored
aggregates.
"""

import csv
import hashlib
import io
import json
import logging
import os
import re
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.parse import urlsplit

from analytics.repository import find_bulk_jobs, find_module_runs
from common.core import canonical_hash
from salesforce.owner_resolution import owner_field_name, resolve_owner_identity
from storage.extract_store import download_extract_to_tempfile
from storage.locator import has_extract_locator


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
NUMERIC_FIELDS = frozenset({"Amount", "Annual_Revenue", "Employees"})
PRESALES_BUSINESS_FIELDS = {
    "Leads": frozenset(
        {
            "First_Name",
            "Last_Name",
            "Full_Name",
            "Company",
            "Email",
            "Phone",
            "Lead_Status",
            "Lead_Source",
            "Industry",
            "Country",
        }
    ),
    "Contacts": frozenset(
        {
            "First_Name",
            "Last_Name",
            "Full_Name",
            "Account_Name",
            "Email",
            "Phone",
            "Mailing_Country",
        }
    ),
    "Accounts": frozenset({"Account_Name", "Phone", "Industry", "Billing_Country"}),
    "Deals": frozenset(
        {
            "Deal_Name",
            "Account_Name",
            "Stage",
            "Pipeline",
            "Amount",
            "Closing_Date",
        }
    ),
}
UNNAMED_RECORD = "Unnamed record"
LOGGER = logging.getLogger(__name__)


def _validator_kind(field_name):
    lowered = field_name.lower()
    if "email" in lowered:
        return "email"
    if "phone" in lowered or lowered in {"mobile", "fax"}:
        return "phone"
    if lowered in {"website", "url"} or lowered.endswith("_url"):
        return "url"
    if field_name in NUMERIC_FIELDS:
        return "number"
    if lowered.endswith("_time") or lowered.endswith("_date"):
        return "datetime"
    return None


def _is_valid(value, validator_kind):
    if validator_kind == "email":
        return EMAIL_PATTERN.fullmatch(value.strip()) is not None
    if validator_kind == "phone":
        digits = re.sub(r"\D", "", value)
        if not digits or set(digits) == {"0"}:
            return False
        return 7 <= len(digits) <= 15
    if validator_kind == "url":
        parsed = urlsplit(value if "://" in value else f"//{value}")
        return bool(parsed.netloc and "." in parsed.netloc)
    if validator_kind == "number":
        try:
            float(value.replace(",", ""))
            return True
        except ValueError:
            return False
    if validator_kind == "datetime":
        try:
            _parse_datetime_pair(value)
            return True
        except ValueError:
            return False
    return True


def _parse_datetime_pair(value):
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"
    parsed = datetime.fromisoformat(candidate)
    normalized = parsed.isoformat()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return normalized, parsed.astimezone(timezone.utc)


def _parse_field_metadata(module_row, field_names):
    raw_metadata = module_row.get("field_metadata_json")
    if not raw_metadata:
        return {name: {"apiName": name, "legacy": True} for name in field_names}
    values = json.loads(raw_metadata)
    if not isinstance(values, list):
        raise ValueError("Stored field metadata is invalid")
    metadata = {
        str(value.get("apiName") or ""): value
        for value in values
        if isinstance(value, dict) and value.get("apiName")
    }
    if set(metadata) != set(field_names):
        raise ValueError("Stored field metadata does not match the field plan")
    return metadata


def _missing_issue_policy(field_name, metadata, module_name, depth_policy):
    if metadata.get("legacy"):
        return {
            "importance": "LEGACY",
            "severity": "MEDIUM",
            "messageCode": "LEGACY_ANALYSIS_VALUE_MISSING",
        }
    if metadata.get("readOnly"):
        return None
    if metadata.get("systemMandatory"):
        importance = "SYSTEM_MANDATORY"
        severity = "HIGH"
        message_code = "SYSTEM_MANDATORY_VALUE_MISSING"
    elif metadata.get("unique"):
        importance = "UNIQUE"
        severity = "HIGH"
        message_code = "UNIQUE_FIELD_VALUE_MISSING"
    elif field_name in PRESALES_BUSINESS_FIELDS.get(module_name, frozenset()):
        importance = "BUSINESS_CRITICAL"
        severity = "MEDIUM"
        message_code = "BUSINESS_CRITICAL_VALUE_MISSING"
    else:
        importance = "OPTIONAL"
        severity = "LOW"
        message_code = "OPTIONAL_VALUE_MISSING"

    allowed = (
        importance in {"SYSTEM_MANDATORY", "UNIQUE"}
        or (
            importance == "BUSINESS_CRITICAL"
            and depth_policy in {"presales", "deep", "full"}
        )
        or (importance == "OPTIONAL" and depth_policy in {"deep", "full"})
    )
    if not allowed:
        return None
    return {
        "importance": importance,
        "severity": severity,
        "messageCode": message_code,
    }


def _build_field_plan(field_names, field_metadata, module_name, depth_policy):
    plan = []
    for field_name in field_names:
        metadata = field_metadata[field_name]
        plan.append(
            {
                "name": field_name,
                "validatorKind": _validator_kind(field_name),
                "missingPolicy": _missing_issue_policy(
                    field_name, metadata, module_name, depth_policy
                ),
                "fieldLabel": str(metadata.get("label") or field_name),
            }
        )
    return tuple(plan)


def _evaluate_record(row, field_plan, header_mapping):
    fields = {}
    issues = []
    for spec in field_plan:
        field_name = spec["name"]
        raw_value = row.get(header_mapping[field_name])
        value = "" if raw_value is None else str(raw_value).strip()
        evaluated = {
            "value": value,
            "kind": spec["validatorKind"],
            "valid": None,
            "normalizedDatetime": None,
            "datetimeUtc": None,
            "number": None,
        }
        if not value:
            policy = spec["missingPolicy"]
            if policy is not None:
                issues.append(
                    {
                        "metricGroup": "COMPLETENESS",
                    }
                )
            fields[field_name] = evaluated
            continue

        kind = spec["validatorKind"]
        if kind == "datetime":
            try:
                normalized, dt_utc = _parse_datetime_pair(value)
                evaluated["valid"] = True
                evaluated["normalizedDatetime"] = normalized
                evaluated["datetimeUtc"] = dt_utc
            except (TypeError, ValueError):
                evaluated["valid"] = False
        elif kind == "number":
            if _is_valid(value, "number"):
                evaluated["valid"] = True
                evaluated["number"] = float(value.replace(",", ""))
            else:
                evaluated["valid"] = False
        elif kind:
            evaluated["valid"] = _is_valid(value, kind)

        if kind and not evaluated["valid"]:
            issues.append({"metricGroup": "VALIDITY"})
        fields[field_name] = evaluated
    return fields, issues


def _record_display_name(fields):
    def value_for(field_name):
        evaluated = fields.get(field_name)
        return evaluated["value"] if evaluated else ""

    person = " ".join(
        part for part in (value_for("First_Name"), value_for("Last_Name")) if part
    ).strip()
    for field_name in ("Deal_Name", "Account_Name", "Full_Name"):
        value = value_for(field_name)
        if value:
            return value
    if person:
        return person
    for field_name in ("Company", "Name"):
        value = value_for(field_name)
        if value:
            return value
    return ""


def _owner_identity(raw_value, owner_directory):
    identity = resolve_owner_identity(raw_value, owner_directory)
    return {
        "ownerKey": identity["ownerKey"],
        "ownerId": identity.get("ownerId") or "",
        "ownerName": identity["ownerName"],
    }


def _header_mapping(headers, field_names):
    headers_by_case = {}
    for header in headers:
        normalized = header.casefold()
        if normalized not in headers_by_case:
            headers_by_case[normalized] = header
    mapping = {name: headers_by_case.get(name.casefold()) for name in field_names}
    if any(header is None for header in mapping.values()):
        raise ValueError("Export is missing planned fields")
    return mapping


@contextmanager
def _open_export_csv(temp_path):
    """Read a Zoho Bulk Read ZIP or a Salesforce Bulk Query CSV."""
    if zipfile.is_zipfile(temp_path):
        with zipfile.ZipFile(temp_path, "r") as archive:
            csv_members = [
                entry
                for entry in archive.infolist()
                if not entry.is_dir() and entry.filename.lower().endswith(".csv")
            ]
            if len(csv_members) != 1:
                raise ValueError("Stored export must contain exactly one CSV file")
            with archive.open(csv_members[0], "r") as raw_csv:
                with io.TextIOWrapper(
                    raw_csv, encoding="utf-8-sig", newline=""
                ) as text_csv:
                    yield csv.DictReader(text_csv)
        return
    with open(temp_path, "r", encoding="utf-8-sig", newline="") as text_csv:
        yield csv.DictReader(text_csv)


def _evaluated_field(fields, *names):
    for name in names:
        evaluated = fields.get(name)
        if evaluated:
            return evaluated
    return {}


def _download_source_zip(bulk_row):
    return download_extract_to_tempfile(
        bulk_row,
        prefix="ada_clean_",
        suffix=".zip",
        require_checksum=False,
    )


def _utc_timestamp(value):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return f"{value.astimezone(timezone.utc).isoformat(timespec='milliseconds')}Z"
    timestamp = str(value or "")
    for date_format in ("%Y-%m-%d %H:%M:%S:%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return f"{datetime.strptime(timestamp, date_format).isoformat(timespec='milliseconds')}Z"
        except ValueError:
            continue
    return timestamp


def _stable_finding_id(scan_id, module_api_name, record_id):
    digest = canonical_hash(
        {
            "scan_id": scan_id,
            "module": module_api_name,
            "crm_record_id": record_id,
            "state": "proper",
        }
    )
    return f"clean_{digest[:32]}"


def _matches_owners(owner_key, owners):
    if not owners:
        return True
    include_unassigned = any(owner == "__unassigned__" for owner in owners)
    owner_keys = [owner for owner in owners if owner != "__unassigned__"]
    if include_unassigned and not owner_key:
        return True
    return owner_key in owner_keys


def _clean_records_from_bulk(bulk_row, module_row, scan_row, owner_directory, owners):
    field_names = json.loads(module_row.get("field_allowlist_json") or "[]")
    if not isinstance(field_names, list) or not field_names:
        raise ValueError("Stored field allowlist is invalid")
    module_api_name = str(module_row.get("module_api_name") or "")
    field_plan = _build_field_plan(
        field_names,
        _parse_field_metadata(module_row, field_names),
        module_api_name,
        scan_row.get("depth_policy"),
    )
    temp_path = _download_source_zip(bulk_row)
    records = []
    try:
        with _open_export_csv(temp_path) as reader:
            mapping = _header_mapping(reader.fieldnames or [], field_names)
            planned_owner_field = owner_field_name(mapping)
            for row in reader:
                fields, issues = _evaluate_record(row, field_plan, mapping)
                missing = sum(
                    1
                    for issue in issues
                    if issue["metricGroup"] == "COMPLETENESS"
                )
                invalid = sum(
                    1
                    for issue in issues
                    if issue["metricGroup"] == "VALIDITY"
                )
                if missing or invalid:
                    continue
                record_id = _evaluated_field(fields, "id", "Id").get("value") or ""
                if not record_id:
                    continue
                owner_identity = {"ownerKey": "", "ownerName": "Unassigned"}
                if planned_owner_field is not None:
                    owner_identity = _owner_identity(
                        _evaluated_field(fields, planned_owner_field).get("value"),
                        owner_directory,
                    )
                owner_key = owner_identity["ownerKey"] if owner_identity["ownerName"] != "Unassigned" else ""
                if not _matches_owners(owner_key, owners):
                    continue
                created = _evaluated_field(fields, "Created_Time", "CreatedDate")
                created_at = created.get("datetimeUtc") or created.get("value") or ""
                display_name = _record_display_name(fields)
                records.append(
                    {
                        "findingId": _stable_finding_id(
                            scan_row.get("scan_id"),
                            module_api_name,
                            record_id,
                        ),
                        "recordName": display_name or None,
                        "recordRef": display_name or UNNAMED_RECORD,
                        "module": module_api_name,
                        "state": "proper",
                        "severity": None,
                        "reason": "No quality issues",
                        "ownerName": owner_identity["ownerName"],
                        "issueCount": 0,
                        "issues": [],
                        "createdTime": _utc_timestamp(created_at),
                        "computedAt": _utc_timestamp(created_at),
                    }
                )
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
    return records


def list_clean_records(zcql, scan_row, modules, owners, owner_directory):
    """Return clean records from stored module exports, in module then CSV order."""
    selected = set(modules)
    records = []
    for module_row in find_module_runs(zcql, scan_row["ROWID"]):
        module_api_name = str(module_row.get("module_api_name") or "")
        if selected and module_api_name not in selected:
            continue
        for bulk_row in find_bulk_jobs(zcql, module_row["ROWID"]):
            if has_extract_locator(bulk_row):
                records.extend(
                    _clean_records_from_bulk(
                        bulk_row,
                        module_row,
                        scan_row,
                        owner_directory,
                        owners,
                    )
                )
    return records


def _rate(numerator, denominator):
    return round(numerator / denominator, 6) if denominator else None


def _accumulate_owner(owners, field_plan, fields, identity):
    owner = owners.setdefault(
        identity["ownerKey"],
        {
            **identity,
            "recordCount": 0,
            "totalCells": 0,
            "populatedCells": 0,
            "checkedValues": 0,
            "invalidValues": 0,
        },
    )
    owner["recordCount"] += 1
    owner["totalCells"] += len(field_plan)
    for spec in field_plan:
        evaluated = fields.get(spec["name"]) or {}
        if not evaluated.get("value"):
            continue
        owner["populatedCells"] += 1
        if evaluated.get("kind"):
            owner["checkedValues"] += 1
            if not evaluated.get("valid"):
                owner["invalidValues"] += 1


def _owner_analytics_candidate(owner):
    payload = {
        "ownerKey": owner["ownerKey"],
        "ownerName": owner.get("ownerName") or "Unassigned",
        "recordCount": int(owner.get("recordCount") or 0),
        "totalCells": int(owner.get("totalCells") or 0),
        "populatedCells": int(owner.get("populatedCells") or 0),
        "checkedValues": int(owner.get("checkedValues") or 0),
        "invalidValues": int(owner.get("invalidValues") or 0),
    }
    payload["emptyCells"] = payload["totalCells"] - payload["populatedCells"]
    payload["completenessRate"] = _rate(payload["populatedCells"], payload["totalCells"])
    payload["validityRate"] = _rate(
        payload["checkedValues"] - payload["invalidValues"],
        payload["checkedValues"],
    )
    aggregate_json = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return {
        "schemaVersion": "owner-quality-v2",
        "ruleVersion": "quality-rules-v1",
        "resultChecksum": hashlib.sha256(aggregate_json.encode("utf-8")).hexdigest(),
        "computedAt": "",
        "data": payload,
    }


def _owner_analytics_from_bulk(bulk_row, module_row, scan_row, owner_directory):
    field_names = json.loads(module_row.get("field_allowlist_json") or "[]")
    if not isinstance(field_names, list) or not field_names:
        raise ValueError("Stored field allowlist is invalid")
    planned_owner_field = owner_field_name(field_names)
    if planned_owner_field is None:
        return []
    module_api_name = str(module_row.get("module_api_name") or "")
    field_plan = _build_field_plan(
        field_names,
        _parse_field_metadata(module_row, field_names),
        module_api_name,
        scan_row.get("depth_policy"),
    )
    temp_path = _download_source_zip(bulk_row)
    owners = {}
    try:
        with _open_export_csv(temp_path) as reader:
            mapping = _header_mapping(reader.fieldnames or [], field_names)
            for row in reader:
                fields, _issues = _evaluate_record(row, field_plan, mapping)
                identity = _owner_identity(
                    _evaluated_field(fields, planned_owner_field).get("value"),
                    owner_directory,
                )
                _accumulate_owner(owners, field_plan, fields, identity)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
    return [
        _owner_analytics_candidate(owner)
        for owner in sorted(
            owners.values(),
            key=lambda item: (
                str(item.get("ownerName") or "").lower(),
                item.get("ownerKey") or "",
            ),
        )
    ]


def list_owner_analytics(zcql, scan_row, module_api_name, owner_directory):
    """Rebuild owner_quality-shaped analytics from the stored Salesforce CSV."""
    selected = str(module_api_name or "")
    collected = []
    for module_row in find_module_runs(zcql, scan_row["ROWID"]):
        if str(module_row.get("module_api_name") or "") != selected:
            continue
        for bulk_row in find_bulk_jobs(zcql, module_row["ROWID"]):
            if has_extract_locator(bulk_row):
                collected.extend(
                    _owner_analytics_from_bulk(
                        bulk_row, module_row, scan_row, owner_directory
                    )
                )
    return collected


def attach_salesforce_owner_analytics(datastore, zcql, scan_row, payload):
    """Fill empty ownerAnalytics from the Salesforce directory + stored CSV."""
    from connections.repository import scan_crm_provider
    from salesforce.owner_resolution import (
        ensure_salesforce_owner_directory,
        load_salesforce_connection_row,
        load_salesforce_owner_directory,
    )

    if scan_crm_provider(scan_row) != "salesforce":
        return payload
    modules = payload.get("modules") or []
    if not modules or all(module.get("ownerAnalytics") for module in modules):
        return payload
    connection = load_salesforce_connection_row(zcql, scan_row)
    directory = {}
    if connection is not None:
        directory = ensure_salesforce_owner_directory(
            datastore, zcql, connection, refresh=False
        ) or load_salesforce_owner_directory(zcql, connection.get("ROWID"))
    for module in modules:
        if module.get("ownerAnalytics"):
            continue
        try:
            module["ownerAnalytics"] = list_owner_analytics(
                zcql,
                scan_row,
                module.get("moduleApiName"),
                directory,
            )
        except Exception as exc:  # noqa: BLE001 - keep module metrics if owners fail
            LOGGER.warning(
                "Could not rebuild Salesforce owner analytics for %s: %s",
                module.get("moduleApiName"),
                exc,
            )
            module["ownerAnalytics"] = []
    return payload
