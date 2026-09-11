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
import os
import re
import tempfile
import zipfile
from datetime import datetime, timezone
from urllib.parse import urlsplit

import zcatalyst_sdk

from analytics.repository import find_bulk_jobs, find_module_runs
from common.core import canonical_hash


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
        digit_count = len(re.sub(r"\D", "", value))
        return 7 <= digit_count <= 15
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
    value = "" if raw_value is None else str(raw_value).strip()
    owner_id = ""
    owner_name = ""
    if value:
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            decoded = None
        if isinstance(decoded, dict):
            owner_id = str(decoded.get("id") or decoded.get("zuid") or "").strip()
            owner_name = str(decoded.get("name") or decoded.get("full_name") or "").strip()
        elif value.isdigit():
            owner_id = value
        else:
            owner_name = value
    if not owner_id and not owner_name:
        owner_name = "Unassigned"
        owner_key = canonical_hash({"owner_state": "unassigned"})
    elif owner_id:
        owner_key = canonical_hash({"crm_user_id": owner_id})
        owner_name = (owner_directory or {}).get(
            owner_key, owner_name or "Unknown owner"
        )
    else:
        owner_key = canonical_hash({"owner_name": owner_name.casefold()})
    return {
        "ownerKey": owner_key,
        "ownerName": owner_name,
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


def _download_source_zip(bulk_row):
    folder_id = os.environ.get("BULK_EXPORT_FOLDER_ID", "")
    if not folder_id.isdigit():
        raise ValueError("BULK_EXPORT_FOLDER_ID is not configured")
    source_file_id = str(bulk_row.get("source_file_id") or "")
    if not source_file_id.isdigit():
        raise ValueError("Bulk Read source file identifier is invalid")

    temp_file = tempfile.NamedTemporaryFile(
        prefix="ada_clean_", suffix=".zip", delete=False
    )
    temp_path = temp_file.name
    source_hash = hashlib.sha256()
    try:
        response = (
            zcatalyst_sdk.initialize()
            .filestore()
            .folder(int(folder_id))
            .get_file_stream(int(source_file_id))
        )
        with temp_file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    source_hash.update(chunk)
                    temp_file.write(chunk)
        checksum = bulk_row.get("source_file_checksum")
        if checksum and source_hash.hexdigest() != checksum:
            raise ValueError("Downloaded File Store checksum does not match")
        return temp_path
    except Exception:
        try:
            temp_file.close()
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        raise


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
                    reader = csv.DictReader(text_csv)
                    mapping = _header_mapping(reader.fieldnames or [], field_names)
                    owner_header = mapping.get("Owner")
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
                        record_id = fields["id"]["value"]
                        if not record_id:
                            continue
                        owner_identity = {"ownerKey": "", "ownerName": "Unassigned"}
                        if owner_header is not None:
                            owner_identity = _owner_identity(
                                fields.get("Owner", {}).get("value"),
                                owner_directory,
                            )
                        owner_key = owner_identity["ownerKey"] if owner_identity["ownerName"] != "Unassigned" else ""
                        if not _matches_owners(owner_key, owners):
                            continue
                        created = fields.get("Created_Time") or {}
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
            if str(bulk_row.get("source_file_id") or "").isdigit():
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
