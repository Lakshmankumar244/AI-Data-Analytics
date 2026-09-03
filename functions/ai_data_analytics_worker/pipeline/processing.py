"""Stream a stored Zoho Bulk Read CSV into checkpointed quality aggregates."""

import csv
import hashlib
import io
import json
import logging
import math
import os
import re
import tempfile
import zipfile
from datetime import datetime, timezone
from urllib.parse import urlsplit


AGGREGATE_SCHEMA_VERSION = "quality-aggregate-v1"
QUALITY_RULE_VERSION = "quality-rules-v1"
DOMAIN_SCHEMA_VERSION = "quality-domains-v2"
DOMAIN_RULE_VERSION = "phase2-domain-rules-v1"
OWNER_SCHEMA_VERSION = "owner-quality-v2"
RECORD_FINDING_SCHEMA_VERSION = "record-findings-v3"
RECORD_FINDING_RULE_VERSION = "record-rules-v3"
MAX_STORED_FINDINGS_PER_MODULE = 40
MAX_STORED_ISSUES_PER_FINDING = 4
MAX_AGGREGATE_JSON_LENGTH = 10000
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
NUMERIC_FIELDS = frozenset({"Amount", "Annual_Revenue", "Employees"})
VALIDATOR_ISSUE_TYPES = {
    "email": "INVALID_EMAIL",
    "phone": "INVALID_PHONE",
    "url": "INVALID_URL",
    "number": "INVALID_NUMBER",
    "datetime": "INVALID_DATETIME",
}
SEVERITY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
PRESALES_BUSINESS_FIELDS = {
    "Leads": frozenset(
        {
            "First_Name",
            "Last_Name",
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
        {"First_Name", "Last_Name", "Account_Name", "Email", "Phone", "Mailing_Country"}
    ),
    "Accounts": frozenset(
        {"Account_Name", "Phone", "Industry", "Billing_Country"}
    ),
    "Deals": frozenset(
        {"Deal_Name", "Account_Name", "Stage", "Pipeline", "Amount", "Closing_Date"}
    ),
}
DUPLICATION_FIELDS = {
    "Leads": frozenset({"Email"}),
    "Contacts": frozenset({"Email"}),
    "Accounts": frozenset({"Account_Name"}),
}
FRESHNESS_THRESHOLDS_DAYS = (90, 180, 365)

logger = logging.getLogger(__name__)


def _foreign_row_id(value):
    if isinstance(value, dict):
        return value.get("ROWID") or value.get("rowid")
    return value


def _numeric_row_id(value, label):
    row_id = str(_foreign_row_id(value))
    if not row_id.isdigit():
        raise ValueError(f"{label} is invalid")
    return row_id


def _query_one(zcql, query, table_name):
    results = zcql.execute_query(query)
    return results[0][table_name] if results else None


def _query_all_rows(zcql, query_prefix, table_name, page_size=300):
    rows = []
    offset = 0
    while True:
        results = zcql.execute_query(
            f"{query_prefix} limit {offset},{page_size}"
        )
        page = [item[table_name] for item in results]
        rows.extend(page)
        if len(page) < page_size:
            return rows
        offset += page_size


def _canonical_json(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )


def _canonical_hash(value):
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _catalyst_datetime_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


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


def _normalized_datetime(value):
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"
    return datetime.fromisoformat(candidate).isoformat()


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
            _normalized_datetime(value)
            return True
        except ValueError:
            return False
    return True


def _datetime_utc(value):
    candidate = str(value or "").strip()
    if candidate.endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"
    parsed = datetime.fromisoformat(candidate)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _new_domain_accumulator(
    field_names, field_metadata, module_name, scan_to, owner_directory
):
    configured_duplicate_fields = DUPLICATION_FIELDS.get(module_name, frozenset())
    duplicate_fields = [
        name
        for name in field_names
        if name != "id"
        and (
            name in configured_duplicate_fields
            or bool(field_metadata.get(name, {}).get("unique"))
        )
    ]
    try:
        cutoff = _datetime_utc(scan_to)
    except (TypeError, ValueError):
        cutoff = None
    return {
        "moduleName": module_name,
        "ownerDirectory": owner_directory,
        "duplicateFields": {
            name: {"observations": 0, "hashes": set()}
            for name in duplicate_fields
        },
        "plausibility": {"checks": 0, "failures": 0, "rules": {}},
        "freshness": {
            "evaluated": 0,
            "scorePoints": 0,
            "buckets": {"0To90": 0, "91To180": 0, "181To365": 0, "over365": 0},
        },
        "integrity": {"checks": 0, "failures": 0, "rules": {}},
        "cutoff": cutoff,
    }


def _duplicate_normalized(field_name, value):
    candidate = str(value or "").strip().casefold()
    if not candidate:
        return ""
    if "phone" in field_name.casefold() or field_name.casefold() in {"mobile", "fax"}:
        return re.sub(r"\D", "", candidate)
    return " ".join(candidate.split())


def _add_plausibility_check(accumulator, rule_id, passed):
    plausibility = accumulator["plausibility"]
    plausibility["checks"] += 1
    rule = plausibility["rules"].setdefault(
        rule_id, {"checksPerformed": 0, "checksFailed": 0}
    )
    rule["checksPerformed"] += 1
    if not passed:
        plausibility["failures"] += 1
        rule["checksFailed"] += 1


def _add_integrity_check(accumulator, rule_id, passed):
    integrity = accumulator["integrity"]
    integrity["checks"] += 1
    rule = integrity["rules"].setdefault(
        rule_id, {"checksPerformed": 0, "checksFailed": 0}
    )
    rule["checksPerformed"] += 1
    if not passed:
        integrity["failures"] += 1
        rule["checksFailed"] += 1


def _add_domain_record(accumulator, row, header_mapping):
    for field_name, stats in accumulator["duplicateFields"].items():
        value = _duplicate_normalized(field_name, row.get(header_mapping[field_name]))
        if not value:
            continue
        if _validator_kind(field_name) and not _is_valid(value, _validator_kind(field_name)):
            continue
        stats["observations"] += 1
        # A 128-bit digest keeps the in-memory uniqueness set bounded without
        # retaining CRM values. The digest never leaves the worker process.
        stats["hashes"].add(hashlib.sha256(value.encode("utf-8")).digest()[:16])

    for field_name in NUMERIC_FIELDS:
        header = header_mapping.get(field_name)
        if not header:
            continue
        value = str(row.get(header) or "").strip()
        if not value or not _is_valid(value, "number"):
            continue
        number = float(value.replace(",", ""))
        passed = (
            math.isfinite(number)
            and number >= 0
            and (field_name != "Employees" or number.is_integer())
        )
        _add_plausibility_check(accumulator, f"{field_name}_NON_NEGATIVE", passed)

    parsed_times = {}
    for field_name in ("Created_Time", "Modified_Time"):
        header = header_mapping.get(field_name)
        value = row.get(header) if header else None
        if not value:
            continue
        try:
            parsed_times[field_name] = _datetime_utc(value)
        except (TypeError, ValueError):
            continue
        cutoff = accumulator["cutoff"]
        if cutoff is not None:
            _add_plausibility_check(
                accumulator, f"{field_name}_NOT_FUTURE", parsed_times[field_name] <= cutoff
            )

    if "Created_Time" in parsed_times and "Modified_Time" in parsed_times:
        _add_plausibility_check(
            accumulator,
            "CREATED_NOT_AFTER_MODIFIED",
            parsed_times["Created_Time"] <= parsed_times["Modified_Time"],
        )

    owner_header = header_mapping.get("Owner")
    if owner_header:
        owner = _owner_identity(row.get(owner_header), accumulator["ownerDirectory"])
        owner_assigned = owner["ownerName"] != "Unassigned"
        _add_integrity_check(accumulator, "OWNER_ASSIGNED", owner_assigned)
        if owner_assigned and owner["ownerId"] and accumulator["ownerDirectory"] is not None:
            _add_integrity_check(
                accumulator,
                "OWNER_ACTIVE",
                owner["ownerKey"] in accumulator["ownerDirectory"],
            )

    if accumulator["moduleName"] in {"Contacts", "Deals"}:
        account_header = header_mapping.get("Account_Name")
        if account_header:
            account_assigned = bool(str(row.get(account_header) or "").strip())
            _add_integrity_check(
                accumulator, "REQUIRED_ACCOUNT_RELATIONSHIP", account_assigned
            )

    modified = parsed_times.get("Modified_Time")
    cutoff = accumulator["cutoff"]
    if modified is None or cutoff is None:
        return
    age_days = max(0, (cutoff - modified).total_seconds() / 86400)
    freshness = accumulator["freshness"]
    freshness["evaluated"] += 1
    if age_days <= FRESHNESS_THRESHOLDS_DAYS[0]:
        freshness["buckets"]["0To90"] += 1
        freshness["scorePoints"] += 100
    elif age_days <= FRESHNESS_THRESHOLDS_DAYS[1]:
        freshness["buckets"]["91To180"] += 1
        freshness["scorePoints"] += 75
    elif age_days <= FRESHNESS_THRESHOLDS_DAYS[2]:
        freshness["buckets"]["181To365"] += 1
        freshness["scorePoints"] += 40
    else:
        freshness["buckets"]["over365"] += 1


def _domain_payload(accumulator):
    duplicate_fields = []
    duplicate_observations = 0
    duplicate_occurrences = 0
    for field_name, stats in accumulator["duplicateFields"].items():
        observations = stats["observations"]
        distinct = len(stats["hashes"])
        duplicates = max(0, observations - distinct)
        duplicate_observations += observations
        duplicate_occurrences += duplicates
        duplicate_fields.append(
            {
                "fieldApiName": field_name,
                "observations": observations,
                "distinctValues": distinct,
                "duplicateOccurrences": duplicates,
            }
        )
    duplication_applicable = duplicate_observations > 0

    plausibility = accumulator["plausibility"]
    plausibility_applicable = plausibility["checks"] > 0
    freshness = accumulator["freshness"]
    freshness_applicable = freshness["evaluated"] > 0
    integrity = accumulator["integrity"]
    integrity_applicable = integrity["checks"] > 0
    return {
        "schemaVersion": DOMAIN_SCHEMA_VERSION,
        "ruleVersion": DOMAIN_RULE_VERSION,
        "domains": {
            "duplication": {
                "applicable": duplication_applicable,
                "score": round(
                    100 * (duplicate_observations - duplicate_occurrences)
                    / duplicate_observations
                ) if duplication_applicable else None,
                "observations": duplicate_observations,
                "duplicateOccurrences": duplicate_occurrences,
                "fields": duplicate_fields,
                "reason": None if duplication_applicable else "No configured identity values were available",
            },
            "plausibility": {
                "applicable": plausibility_applicable,
                "score": round(
                    100 * (plausibility["checks"] - plausibility["failures"])
                    / plausibility["checks"]
                ) if plausibility_applicable else None,
                "checksPerformed": plausibility["checks"],
                "checksFailed": plausibility["failures"],
                "rules": [
                    {"ruleId": rule_id, **counts}
                    for rule_id, counts in sorted(plausibility["rules"].items())
                ],
                "reason": None if plausibility_applicable else "No applicable numeric or temporal values were available",
            },
            "freshness": {
                "applicable": freshness_applicable,
                "score": round(freshness["scorePoints"] / freshness["evaluated"])
                if freshness_applicable else None,
                "recordsEvaluated": freshness["evaluated"],
                "scorePoints": freshness["scorePoints"],
                "thresholdsDays": list(FRESHNESS_THRESHOLDS_DAYS),
                "buckets": freshness["buckets"],
                "reason": None if freshness_applicable else "No valid Modified Time values were available",
            },
            "integrity": {
                "applicable": integrity_applicable,
                "score": round(
                    100 * (integrity["checks"] - integrity["failures"])
                    / integrity["checks"]
                ) if integrity_applicable else None,
                "checksPerformed": integrity["checks"],
                "checksFailed": integrity["failures"],
                "rules": [
                    {"ruleId": rule_id, **counts}
                    for rule_id, counts in sorted(integrity["rules"].items())
                ],
                "reason": None if integrity_applicable else "No supported relationship checks were available",
            },
            "config": {
                "applicable": False,
                "score": None,
                "reason": "Configuration scoring requires approved layout and workflow policy",
            },
            "pii": {
                "applicable": False,
                "score": None,
                "reason": "PII and access scoring requires profile-permission evidence and a sensitive-field policy",
            },
            "automation": {
                "applicable": False,
                "score": None,
                "reason": "Automation scoring requires function and scheduler execution evidence",
            },
        },
    }


def _new_partial(field_names):
    return {
        "schemaVersion": AGGREGATE_SCHEMA_VERSION,
        "ruleVersion": QUALITY_RULE_VERSION,
        "recordCount": 0,
        "fields": {
            field_name: {
                "populated": 0,
                "empty": 0,
                "checked": 0,
                "invalid": 0,
            }
            for field_name in field_names
        },
        "temporal": {},
    }


def _add_record(partial, row, field_names, header_mapping):
    partial["recordCount"] += 1
    for field_name in field_names:
        raw_value = row.get(header_mapping[field_name])
        value = "" if raw_value is None else str(raw_value).strip()
        stats = partial["fields"][field_name]
        if not value:
            stats["empty"] += 1
            continue

        stats["populated"] += 1
        validator_kind = _validator_kind(field_name)
        if validator_kind:
            stats["checked"] += 1
            if not _is_valid(value, validator_kind):
                stats["invalid"] += 1

        if validator_kind == "datetime" and _is_valid(value, validator_kind):
            normalized = _normalized_datetime(value)
            bounds = partial["temporal"].setdefault(
                field_name, {"minimum": normalized, "maximum": normalized}
            )
            bounds["minimum"] = min(bounds["minimum"], normalized)
            bounds["maximum"] = max(bounds["maximum"], normalized)


def _parse_field_metadata(module_row, field_names):
    raw_metadata = module_row.get("field_metadata_json")
    if not raw_metadata:
        return {name: {"apiName": name, "legacy": True} for name in field_names}
    try:
        values = json.loads(raw_metadata)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Stored field metadata is invalid") from exc
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


def _record_finding_candidate(
    row,
    field_names,
    field_metadata,
    header_mapping,
    owner_directory,
    scan_row,
    module_row,
    source_checksum,
):
    record_id = str(row.get(header_mapping["id"]) or "").strip()
    if not record_id:
        raise ValueError("Export record is missing its CRM record identifier")

    issues = []
    for field_name in field_names:
        raw_value = row.get(header_mapping[field_name])
        value = "" if raw_value is None else str(raw_value).strip()
        if not value:
            policy = _missing_issue_policy(
                field_name,
                field_metadata[field_name],
                module_row["module_api_name"],
                scan_row["depth_policy"],
            )
            if policy is None:
                continue
            issues.append(
                {
                    "fieldApiName": field_name,
                    "metricGroup": "COMPLETENESS",
                    "issueType": "MISSING_VALUE",
                    "severity": policy["severity"],
                    "messageCode": policy["messageCode"],
                    "validator": None,
                    "importance": policy["importance"],
                    "fieldLabel": str(
                        field_metadata[field_name].get("label") or field_name
                    ),
                }
            )
            continue
        validator_kind = _validator_kind(field_name)
        if validator_kind and not _is_valid(value, validator_kind):
            issue_type = VALIDATOR_ISSUE_TYPES[validator_kind]
            issues.append(
                {
                    "fieldApiName": field_name,
                    "metricGroup": "VALIDITY",
                    "issueType": issue_type,
                    "severity": "HIGH",
                    "messageCode": f"{issue_type}_FORMAT",
                    "validator": validator_kind,
                    "importance": None,
                    "fieldLabel": str(
                        field_metadata[field_name].get("label") or field_name
                    ),
                }
            )

    if not issues:
        return None

    record_key = _canonical_hash(
        {
            "scan_id": scan_row["scan_id"],
            "module": module_row["module_api_name"],
            "crm_record_id": record_id,
        }
    )
    finding_key = _canonical_hash(
        {
            "record_key": record_key,
            "source_checksum": source_checksum,
            "schema_version": RECORD_FINDING_SCHEMA_VERSION,
            "rule_version": RECORD_FINDING_RULE_VERSION,
        }
    )
    owner_key = ""
    if "Owner" in header_mapping:
        owner_identity = _owner_identity(
            row.get(header_mapping["Owner"]), owner_directory
        )
        if owner_identity["ownerName"] != "Unassigned":
            owner_key = owner_identity["ownerKey"]
    highest_severity = max(
        (issue["severity"] for issue in issues), key=SEVERITY_RANK.get
    )
    return {
        "findingKey": finding_key,
        "recordKey": record_key,
        "crmRecordId": record_id,
        "ownerKey": owner_key,
        "highestSeverity": highest_severity,
        "missingCount": sum(
            1 for issue in issues if issue["metricGroup"] == "COMPLETENESS"
        ),
        "invalidCount": sum(
            1 for issue in issues if issue["metricGroup"] == "VALIDITY"
        ),
        "staleCount": 0,
        "issues": issues,
    }


def _insert_rows_in_chunks(table, rows, chunk_size=100):
    for start in range(0, len(rows), chunk_size):
        table.insert_rows(rows[start : start + chunk_size])


def _persist_record_findings(app, scan_row, module_row, batch_row, source_checksum, findings):
    if not findings:
        return {"affectedRecordCount": 0, "issueCount": 0}

    zcql = app.zcql()
    datastore = app.datastore()
    batch_row_id = _numeric_row_id(batch_row.get("ROWID"), "Processing batch link")
    existing_rows = _query_all_rows(
        zcql,
        "select * from record_quality_findings where "
        f"processing_batch_row_id = {batch_row_id}",
        "record_quality_findings",
    )
    existing_by_key = {
        str(row.get("finding_key") or ""): row
        for row in existing_rows
    }
    finding_table = datastore.table("record_quality_findings")
    issue_table = datastore.table("record_quality_issues")
    computed_at = _catalyst_datetime_now()
    pending_issue_rows = []

    new_finding_rows = []
    for finding in findings:
        if finding["findingKey"] in existing_by_key:
            continue
        row_data = {
            "finding_id": f"finding_{finding['findingKey'][:32]}",
            "finding_key": finding["findingKey"],
            "scan_row_id": scan_row["ROWID"],
            "scan_module_row_id": module_row["ROWID"],
            "processing_batch_row_id": batch_row["ROWID"],
            "record_key": finding["recordKey"],
            "crm_record_id": finding["crmRecordId"],
            "module_api_name": module_row["module_api_name"],
            "issue_count": len(finding["issues"]),
            "missing_count": finding["missingCount"],
            "invalid_count": finding["invalidCount"],
            "stale_count": finding["staleCount"],
            "highest_severity": finding["highestSeverity"],
            "status": "DETECTED",
            "schema_version": RECORD_FINDING_SCHEMA_VERSION,
            "rule_version": RECORD_FINDING_RULE_VERSION,
            "source_checksum": source_checksum,
            "computed_at": computed_at,
        }
        if finding["ownerKey"]:
            row_data["owner_key"] = finding["ownerKey"]
        new_finding_rows.append(row_data)

    _insert_rows_in_chunks(finding_table, new_finding_rows)
    if new_finding_rows:
        stored_rows = _query_all_rows(
            zcql,
            "select * from record_quality_findings where "
            f"processing_batch_row_id = {batch_row_id}",
            "record_quality_findings",
        )
        existing_by_key = {
            str(row.get("finding_key") or ""): row for row in stored_rows
        }

    existing_issue_keys = set()
    if existing_rows:
        record_keys = [finding["recordKey"] for finding in findings]
        for start in range(0, len(record_keys), 25):
            key_values = ",".join(
                f"'{record_key}'" for record_key in record_keys[start : start + 25]
            )
            issue_rows = _query_all_rows(
                zcql,
                "select issue_key from record_quality_issues where "
                f"record_key in ({key_values}) and "
                f"schema_version = '{RECORD_FINDING_SCHEMA_VERSION}'",
                "record_quality_issues",
            )
            existing_issue_keys.update(
                str(row.get("issue_key") or "") for row in issue_rows
            )

    for finding in findings:
        finding_key = finding["findingKey"]
        stored_finding = existing_by_key.get(finding_key)
        if stored_finding is None:
            raise ValueError("Stored record finding could not be resolved")
        finding_row_id = _numeric_row_id(
            stored_finding.get("ROWID"), "Record finding identifier"
        )
        for issue in finding["issues"][:MAX_STORED_ISSUES_PER_FINDING]:
            issue_key = _canonical_hash(
                {
                    "finding_key": finding_key,
                    "field": issue["fieldApiName"],
                    "issue_type": issue["issueType"],
                    "schema_version": RECORD_FINDING_SCHEMA_VERSION,
                }
            )
            if issue_key in existing_issue_keys:
                continue
            metadata = {
                "messageCode": issue["messageCode"],
                "validator": issue["validator"],
                "importance": issue["importance"],
                "fieldLabel": issue["fieldLabel"],
            }
            pending_issue_rows.append(
                {
                    "issue_id": f"issue_{issue_key[:32]}",
                    "issue_key": issue_key,
                    "finding_row_id": finding_row_id,
                    "scan_row_id": scan_row["ROWID"],
                    "scan_module_row_id": module_row["ROWID"],
                    "record_key": finding["recordKey"],
                    "field_api_name": issue["fieldApiName"],
                    "metric_group": issue["metricGroup"],
                    "issue_type": issue["issueType"],
                    "severity": issue["severity"],
                    "rule_id": _canonical_hash(
                        {
                            "field": issue["fieldApiName"],
                            "issue_type": issue["issueType"],
                            "rule_version": RECORD_FINDING_RULE_VERSION,
                        }
                    ),
                    "issue_metadata_json": _canonical_json(metadata),
                    "schema_version": RECORD_FINDING_SCHEMA_VERSION,
                    "rule_version": RECORD_FINDING_RULE_VERSION,
                    "computed_at": computed_at,
                }
            )
    _insert_rows_in_chunks(issue_table, pending_issue_rows)

    return {
        "affectedRecordCount": len(findings),
        "issueCount": sum(len(finding["issues"]) for finding in findings),
    }


def _load_owner_directory(zcql, scan_row):
    connection_row_id = _numeric_row_id(
        scan_row.get("connection_row_id"), "Scan connection link"
    )
    try:
        results = zcql.execute_query(
            "select * from zoho_connection_users where "
            f"connection_row_id = {connection_row_id} and status = 'ACTIVE'"
        )
    except Exception as exc:  # noqa: BLE001 - owner names are optional metadata
        logger.exception("Could not read cached CRM user directory: %s", exc)
        return None
    try:
        rows = (item["zoho_connection_users"] for item in results)
        directory = {
            str(row.get("crm_user_key") or ""): str(
                row.get("display_name") or "Unknown owner"
            )
            for row in rows
            if row.get("crm_user_key")
        }
        # A CRM account always has at least the current active user. Treat an
        # empty cache as unavailable evidence so records are not falsely marked
        # as owned by inactive users after a failed directory refresh.
        return directory or None
    except (KeyError, TypeError) as exc:
        logger.exception("Cached CRM user directory was malformed: %s", exc)
        return None


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
        owner_key = _canonical_hash({"owner_state": "unassigned"})
    elif owner_id:
        owner_key = _canonical_hash({"crm_user_id": owner_id})
        owner_name = (owner_directory or {}).get(
            owner_key, owner_name or "Unknown owner"
        )
    else:
        owner_key = _canonical_hash({"owner_name": owner_name.casefold()})
    return {
        "ownerKey": owner_key,
        "ownerId": owner_id,
        "ownerName": owner_name,
    }


def _new_owner_partial(identity):
    return {
        **identity,
        "recordCount": 0,
        "totalCells": 0,
        "populatedCells": 0,
        "checkedValues": 0,
        "invalidValues": 0,
    }


def _add_owner_record(
    owner_partials, row, field_names, header_mapping, owner_directory
):
    identity = _owner_identity(
        row.get(header_mapping["Owner"]), owner_directory
    )
    owner = owner_partials.setdefault(
        identity["ownerKey"], _new_owner_partial(identity)
    )
    owner["recordCount"] += 1
    owner["totalCells"] += len(field_names)
    for field_name in field_names:
        raw_value = row.get(header_mapping[field_name])
        value = "" if raw_value is None else str(raw_value).strip()
        if not value:
            continue
        owner["populatedCells"] += 1
        validator_kind = _validator_kind(field_name)
        if validator_kind:
            owner["checkedValues"] += 1
            if not _is_valid(value, validator_kind):
                owner["invalidValues"] += 1


def _owner_row_payload(owner):
    return {
        "ownerKey": owner["ownerKey"],
        "ownerId": owner.get("ownerId") or "",
        "ownerName": owner.get("ownerName") or "Unassigned",
        "recordCount": int(owner.get("recordCount") or 0),
        "totalCells": int(owner.get("totalCells") or 0),
        "populatedCells": int(owner.get("populatedCells") or 0),
        "checkedValues": int(owner.get("checkedValues") or 0),
        "invalidValues": int(owner.get("invalidValues") or 0),
    }


def _persist_batch_owners(app, scan_row, module_row, batch_row, source_checksum, owners):
    zcql = app.zcql()
    table = app.datastore().table("owner_batch_aggregates")
    for owner in owners.values():
        payload = _owner_row_payload(owner)
        result_checksum = hashlib.sha256(
            _canonical_json(payload).encode("utf-8")
        ).hexdigest()
        aggregate_key = _canonical_hash(
            {
                "batch_row_id": str(batch_row["ROWID"]),
                "owner_key": payload["ownerKey"],
                "source_checksum": source_checksum,
                "schema_version": OWNER_SCHEMA_VERSION,
            }
        )
        existing = _query_one(
            zcql,
            "select * from owner_batch_aggregates where "
            f"aggregate_key = '{aggregate_key}' limit 1",
            "owner_batch_aggregates",
        )
        row_data = {
            "aggregate_id": f"owneragg_{aggregate_key[:32]}",
            "aggregate_key": aggregate_key,
            "scan_row_id": scan_row["ROWID"],
            "scan_module_row_id": module_row["ROWID"],
            "processing_batch_row_id": batch_row["ROWID"],
            "owner_key": payload["ownerKey"],
            "owner_name": payload["ownerName"],
            "record_count": payload["recordCount"],
            "total_cells": payload["totalCells"],
            "populated_cells": payload["populatedCells"],
            "checked_values": payload["checkedValues"],
            "invalid_values": payload["invalidValues"],
            "schema_version": OWNER_SCHEMA_VERSION,
            "result_checksum": result_checksum,
            "computed_at": _catalyst_datetime_now(),
        }
        if payload["ownerId"]:
            row_data["owner_id"] = payload["ownerId"]
        if existing:
            if existing.get("result_checksum") != result_checksum:
                row_data["ROWID"] = existing["ROWID"]
                table.update_row(row_data)
        else:
            table.insert_row(row_data)


def _merge_owner_rows(owner_rows, batch_row_ids):
    merged = {}
    for row in owner_rows:
        batch_row_id = str(_foreign_row_id(row.get("processing_batch_row_id")) or "")
        if batch_row_id not in batch_row_ids or row.get("schema_version") != OWNER_SCHEMA_VERSION:
            continue
        owner_key = str(row.get("owner_key") or "")
        if not owner_key:
            continue
        owner = merged.setdefault(
            owner_key,
            _new_owner_partial(
                {
                    "ownerKey": owner_key,
                    "ownerId": str(row.get("owner_id") or ""),
                    "ownerName": str(row.get("owner_name") or "Unassigned"),
                }
            ),
        )
        for target, source in (
            ("recordCount", "record_count"),
            ("totalCells", "total_cells"),
            ("populatedCells", "populated_cells"),
            ("checkedValues", "checked_values"),
            ("invalidValues", "invalid_values"),
        ):
            owner[target] += int(row.get(source) or 0)
    return merged


def _parse_partial(batch_row, source_checksum):
    if batch_row.get("input_checksum") != source_checksum:
        return None
    try:
        partial = json.loads(batch_row.get("partial_aggregate_json") or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if (
        not isinstance(partial, dict)
        or partial.get("schemaVersion") != AGGREGATE_SCHEMA_VERSION
        or partial.get("ruleVersion") != QUALITY_RULE_VERSION
    ):
        return None
    return partial


def _merge_partials(partials, field_names):
    merged = _new_partial(field_names)
    for partial in partials:
        merged["recordCount"] += int(partial.get("recordCount") or 0)
        partial_fields = partial.get("fields") or {}
        if set(partial_fields) != set(field_names):
            raise ValueError("Batch aggregate fields do not match the export plan")
        for field_name in field_names:
            for counter in ("populated", "empty", "checked", "invalid"):
                merged["fields"][field_name][counter] += int(
                    partial_fields[field_name].get(counter) or 0
                )
        for field_name, bounds in (partial.get("temporal") or {}).items():
            merged_bounds = merged["temporal"].setdefault(
                field_name,
                {"minimum": bounds["minimum"], "maximum": bounds["maximum"]},
            )
            merged_bounds["minimum"] = min(
                merged_bounds["minimum"], bounds["minimum"]
            )
            merged_bounds["maximum"] = max(
                merged_bounds["maximum"], bounds["maximum"]
            )
    return merged


def _rate(numerator, denominator):
    return round(numerator / denominator, 6) if denominator else None


def _metric_payloads(aggregate, field_names, domain_payload):
    record_count = aggregate["recordCount"]
    total_cells = record_count * len(field_names)
    populated_cells = sum(
        aggregate["fields"][name]["populated"] for name in field_names
    )
    checked_values = sum(
        aggregate["fields"][name]["checked"] for name in field_names
    )
    invalid_values = sum(
        aggregate["fields"][name]["invalid"] for name in field_names
    )
    return {
        "summary": {
            "recordCount": record_count,
            "fieldsAnalyzed": len(field_names),
            "totalCells": total_cells,
            "populatedCells": populated_cells,
            "emptyCells": total_cells - populated_cells,
            "completenessRate": _rate(populated_cells, total_cells),
            "checkedValues": checked_values,
            "invalidValues": invalid_values,
            "validityRate": _rate(checked_values - invalid_values, checked_values),
        },
        "completeness": {
            "fields": {
                name: {
                    "populated": aggregate["fields"][name]["populated"],
                    "empty": aggregate["fields"][name]["empty"],
                    "rate": _rate(
                        aggregate["fields"][name]["populated"], record_count
                    ),
                }
                for name in field_names
            }
        },
        "validity": {
            "fields": {
                name: {
                    "checked": aggregate["fields"][name]["checked"],
                    "invalid": aggregate["fields"][name]["invalid"],
                    "rate": _rate(
                        aggregate["fields"][name]["checked"]
                        - aggregate["fields"][name]["invalid"],
                        aggregate["fields"][name]["checked"],
                    ),
                }
                for name in field_names
                if aggregate["fields"][name]["checked"]
            }
        },
        "temporal": {"fields": aggregate["temporal"]},
        "domains": domain_payload,
    }


def _persist_results(
    app, scan_row, module_row, bulk_row, aggregate, field_names, domain_payload
):
    zcql = app.zcql()
    result_table = app.datastore().table("analytics_results")
    metric_payloads = _metric_payloads(aggregate, field_names, domain_payload)
    source_checksum = bulk_row["source_file_checksum"]
    created_count = 0
    for metric_group, payload in metric_payloads.items():
        schema_version = (
            DOMAIN_SCHEMA_VERSION if metric_group == "domains" else AGGREGATE_SCHEMA_VERSION
        )
        rule_version = (
            DOMAIN_RULE_VERSION if metric_group == "domains" else QUALITY_RULE_VERSION
        )
        aggregate_json = _canonical_json(payload)
        if len(aggregate_json) > MAX_AGGREGATE_JSON_LENGTH:
            raise ValueError(f"Analytics result {metric_group} exceeds 10000 characters")
        result_checksum = hashlib.sha256(aggregate_json.encode("utf-8")).hexdigest()
        result_key = _canonical_hash(
            {
                "scan_id": scan_row["scan_id"],
                "module": module_row["module_api_name"],
                "metric_group": metric_group,
                "source_checksum": source_checksum,
                "schema_version": schema_version,
                "rule_version": rule_version,
            }
        )
        existing = _query_one(
            zcql,
            f"select * from analytics_results where result_key = '{result_key}' limit 1",
            "analytics_results",
        )
        if existing:
            if existing.get("result_checksum") != result_checksum:
                raise ValueError("Existing analytics result checksum does not match")
            continue
        result_table.insert_row(
            {
                "result_id": f"result_{result_key[:32]}",
                "result_key": result_key,
                "scan_row_id": scan_row["ROWID"],
                "scan_module_row_id": module_row["ROWID"],
                "result_scope": "MODULE",
                "module_api_name": module_row["module_api_name"],
                "metric_group": metric_group,
                "status": "COMPUTED",
                "schema_version": schema_version,
                "rule_version": rule_version,
                "source_record_count": aggregate["recordCount"],
                "aggregate_json": aggregate_json,
                "result_checksum": result_checksum,
                "computed_at": _catalyst_datetime_now(),
                "controlled_error_code": "",
            }
        )
        created_count += 1
    return {"resultCount": len(metric_payloads), "createdResultCount": created_count}


def _persist_record_finding_summary(app, scan_row, module_row, bulk_row, summary):
    issue_groups = sorted(
        summary.get("issueGroups", {}).values(),
        key=lambda group: (
            str(group.get("fieldApiName") or "").lower(),
            str(group.get("issueType") or ""),
            str(group.get("importance") or ""),
        ),
    )
    payload = {
        "measured": True,
        "affectedRecordCount": int(summary.get("affectedRecordCount") or 0),
        "issueCount": int(summary.get("issueCount") or 0),
        "missingIssueCount": int(summary.get("missingIssueCount") or 0),
        "invalidIssueCount": int(summary.get("invalidIssueCount") or 0),
        "staleIssueCount": 0,
        "storedSampleCount": int(summary.get("storedSampleCount") or 0),
        "sampleLimit": MAX_STORED_FINDINGS_PER_MODULE,
        "issueGroups": issue_groups,
    }
    aggregate_json = _canonical_json(payload)
    if len(aggregate_json) > MAX_AGGREGATE_JSON_LENGTH:
        raise ValueError("Record finding summary exceeds 10000 characters")
    result_checksum = hashlib.sha256(aggregate_json.encode("utf-8")).hexdigest()
    source_checksum = bulk_row["source_file_checksum"]
    result_key = _canonical_hash(
        {
            "scan_id": scan_row["scan_id"],
            "module": module_row["module_api_name"],
            "metric_group": "record_findings",
            "source_checksum": source_checksum,
            "schema_version": RECORD_FINDING_SCHEMA_VERSION,
            "rule_version": RECORD_FINDING_RULE_VERSION,
        }
    )
    zcql = app.zcql()
    existing = _query_one(
        zcql,
        f"select * from analytics_results where result_key = '{result_key}' limit 1",
        "analytics_results",
    )
    if existing:
        if existing.get("result_checksum") != result_checksum:
            raise ValueError("Existing record finding summary checksum does not match")
        return False
    app.datastore().table("analytics_results").insert_row(
        {
            "result_id": f"result_{result_key[:32]}",
            "result_key": result_key,
            "scan_row_id": scan_row["ROWID"],
            "scan_module_row_id": module_row["ROWID"],
            "result_scope": "MODULE",
            "module_api_name": module_row["module_api_name"],
            "metric_group": "record_findings",
            "status": "COMPUTED",
            "schema_version": RECORD_FINDING_SCHEMA_VERSION,
            "rule_version": RECORD_FINDING_RULE_VERSION,
            "source_record_count": int(bulk_row.get("provider_record_count") or 0),
            "aggregate_json": aggregate_json,
            "result_checksum": result_checksum,
            "computed_at": _catalyst_datetime_now(),
            "controlled_error_code": "",
        }
    )
    return True


def _persist_owner_results(app, scan_row, module_row, bulk_row, owners):
    zcql = app.zcql()
    table = app.datastore().table("analytics_results")
    source_checksum = bulk_row["source_file_checksum"]
    created_count = 0
    for owner in owners.values():
        payload = _owner_row_payload(owner)
        # The stable owner hash is sufficient for the report; do not expose
        # the provider's raw user identifier in the final API aggregate.
        payload.pop("ownerId", None)
        payload.update(
            {
                "emptyCells": payload["totalCells"] - payload["populatedCells"],
                "completenessRate": _rate(
                    payload["populatedCells"], payload["totalCells"]
                ),
                "validityRate": _rate(
                    payload["checkedValues"] - payload["invalidValues"],
                    payload["checkedValues"],
                ),
            }
        )
        aggregate_json = _canonical_json(payload)
        if len(aggregate_json) > MAX_AGGREGATE_JSON_LENGTH:
            raise ValueError("Owner analytics result exceeds 10000 characters")
        result_checksum = hashlib.sha256(aggregate_json.encode("utf-8")).hexdigest()
        result_key = _canonical_hash(
            {
                "scan_id": scan_row["scan_id"],
                "module": module_row["module_api_name"],
                "owner_key": payload["ownerKey"],
                "metric_group": "owner_quality",
                "source_checksum": source_checksum,
                "schema_version": OWNER_SCHEMA_VERSION,
                "rule_version": QUALITY_RULE_VERSION,
            }
        )
        existing = _query_one(
            zcql,
            f"select * from analytics_results where result_key = '{result_key}' limit 1",
            "analytics_results",
        )
        if existing:
            if existing.get("result_checksum") != result_checksum:
                raise ValueError("Existing owner result checksum does not match")
            continue
        table.insert_row(
            {
                "result_id": f"ownerresult_{result_key[:32]}",
                "result_key": result_key,
                "scan_row_id": scan_row["ROWID"],
                "scan_module_row_id": module_row["ROWID"],
                "result_scope": "OWNER",
                "module_api_name": module_row["module_api_name"],
                "metric_group": "owner_quality",
                "status": "COMPUTED",
                "schema_version": OWNER_SCHEMA_VERSION,
                "rule_version": QUALITY_RULE_VERSION,
                "source_record_count": payload["recordCount"],
                "aggregate_json": aggregate_json,
                "result_checksum": result_checksum,
                "computed_at": _catalyst_datetime_now(),
                "controlled_error_code": "",
            }
        )
        created_count += 1
    return {"resultCount": len(owners), "createdResultCount": created_count}


def _download_source_zip(app, bulk_row):
    folder_id = os.environ.get("BULK_EXPORT_FOLDER_ID", "")
    if not folder_id.isdigit():
        raise ValueError("BULK_EXPORT_FOLDER_ID is not configured")
    source_file_id = str(bulk_row.get("source_file_id") or "")
    if not source_file_id.isdigit():
        raise ValueError("Bulk Read source file identifier is invalid")

    temp_file = tempfile.NamedTemporaryFile(prefix="ada_bulk_", suffix=".zip", delete=False)
    temp_path = temp_file.name
    source_hash = hashlib.sha256()
    try:
        response = (
            app.filestore()
            .folder(int(folder_id))
            .get_file_stream(int(source_file_id))
        )
        with temp_file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    source_hash.update(chunk)
                    temp_file.write(chunk)
        if source_hash.hexdigest() != bulk_row.get("source_file_checksum"):
            raise ValueError("Downloaded File Store checksum does not match")
        return temp_path
    except Exception:
        try:
            temp_file.close()
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        raise


def process_and_finalize(app, task_row):
    """Process every planned batch, checkpoint it, then persist module results."""
    datastore = app.datastore()
    zcql = app.zcql()
    bulk_row_id = _numeric_row_id(task_row.get("bulk_job_row_id"), "Bulk job link")
    bulk_row = _query_one(
        zcql,
        f"select * from bulk_read_jobs where ROWID = {bulk_row_id} limit 1",
        "bulk_read_jobs",
    )
    if not bulk_row:
        raise ValueError("Bulk Read job was not found")
    if bulk_row.get("next_page_token"):
        raise ValueError("Multi-page Bulk Read processing is not implemented yet")
    if bulk_row.get("status") not in {
        "PROCESSING_PLANNED",
        "PROCESSING",
        "PROCESSED",
    }:
        raise ValueError(f"Export cannot be processed from state {bulk_row.get('status')}")

    module_row_id = _numeric_row_id(
        bulk_row.get("scan_module_row_id"), "Scan module link"
    )
    module_row = _query_one(
        zcql,
        f"select * from scan_module_runs where ROWID = {module_row_id} limit 1",
        "scan_module_runs",
    )
    if not module_row:
        raise ValueError("Scan module was not found")
    scan_row_id = _numeric_row_id(module_row.get("scan_row_id"), "Scan link")
    scan_row = _query_one(
        zcql,
        f"select * from scan_jobs where ROWID = {scan_row_id} limit 1",
        "scan_jobs",
    )
    if not scan_row:
        raise ValueError("Scan was not found")
    owner_directory = _load_owner_directory(zcql, scan_row)

    try:
        field_names = json.loads(module_row.get("field_allowlist_json") or "[]")
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Stored field allowlist is invalid") from exc
    if not isinstance(field_names, list) or not field_names:
        raise ValueError("Stored field allowlist is invalid")
    field_metadata = _parse_field_metadata(module_row, field_names)
    domain_accumulator = _new_domain_accumulator(
        field_names,
        field_metadata,
        str(module_row.get("module_api_name") or ""),
        scan_row.get("to_utc"),
        owner_directory,
    )

    batch_results = zcql.execute_query(
        f"select * from processing_batches where bulk_job_row_id = {bulk_row_id}"
    )
    batch_rows = sorted(
        (result["processing_batches"] for result in batch_results),
        key=lambda row: int(row["batch_number"]),
    )
    expected_count = int(bulk_row.get("provider_record_count") or 0)
    expected_batch_count = (expected_count + 4999) // 5000
    if len(batch_rows) != expected_batch_count:
        raise ValueError("Processing batch count does not match the export plan")

    datastore.table("bulk_read_jobs").update_row(
        {"ROWID": bulk_row["ROWID"], "status": "PROCESSING"}
    )
    datastore.table("scan_module_runs").update_row(
        {"ROWID": module_row["ROWID"], "status": "PROCESSING"}
    )

    temp_path = _download_source_zip(app, bulk_row)
    partials = []
    records_seen = 0
    finding_summary = {
        "affectedRecordCount": 0,
        "issueCount": 0,
        "missingIssueCount": 0,
        "invalidIssueCount": 0,
        "storedSampleCount": 0,
        "issueGroups": {},
    }
    remaining_finding_samples = MAX_STORED_FINDINGS_PER_MODULE
    batch_table = datastore.table("processing_batches")
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
                with io.TextIOWrapper(raw_csv, encoding="utf-8-sig", newline="") as text_csv:
                    reader = csv.DictReader(text_csv)
                    headers = reader.fieldnames or []
                    headers_by_case = {}
                    ambiguous_headers = set()
                    for header in headers:
                        normalized_header = header.casefold()
                        if normalized_header in headers_by_case:
                            ambiguous_headers.add(normalized_header)
                        else:
                            headers_by_case[normalized_header] = header
                    if ambiguous_headers:
                        raise ValueError(
                            "Export contains ambiguous case-insensitive headers"
                        )
                    header_mapping = {
                        name: headers_by_case.get(name.casefold()) for name in field_names
                    }
                    missing_fields = [
                        name for name, header in header_mapping.items() if header is None
                    ]
                    if missing_fields:
                        raise ValueError(
                            "Export is missing planned fields: " + ", ".join(missing_fields)
                        )
                    owner_field_available = "Owner" in header_mapping

                    for batch_row in batch_rows:
                        source_record_count = int(batch_row["source_record_count"])
                        reusable_partial = None
                        if batch_row.get("status") == "COMPLETED":
                            reusable_partial = _parse_partial(
                                batch_row, bulk_row["source_file_checksum"]
                            )
                        partial = reusable_partial or _new_partial(field_names)
                        owner_partials = {}
                        record_findings = []
                        if reusable_partial is None:
                            batch_table.update_row(
                                {
                                    "ROWID": batch_row["ROWID"],
                                    "status": "PROCESSING",
                                    "attempt_count": int(
                                        batch_row.get("attempt_count") or 0
                                    )
                                    + 1,
                                    "started_at": _catalyst_datetime_now(),
                                    "controlled_error_code": "",
                                }
                            )

                        for _ in range(source_record_count):
                            try:
                                row = next(reader)
                            except StopIteration as exc:
                                raise ValueError(
                                    "Export contains fewer records than planned"
                                ) from exc
                            records_seen += 1
                            _add_domain_record(domain_accumulator, row, header_mapping)
                            if reusable_partial is None:
                                _add_record(
                                    partial, row, field_names, header_mapping
                                )
                            if owner_field_available:
                                _add_owner_record(
                                    owner_partials,
                                    row,
                                    field_names,
                                    header_mapping,
                                    owner_directory,
                                )
                            finding = _record_finding_candidate(
                                row,
                                field_names,
                                field_metadata,
                                header_mapping,
                                owner_directory,
                                scan_row,
                                module_row,
                                bulk_row["source_file_checksum"],
                            )
                            if finding is not None:
                                record_findings.append(finding)

                        if reusable_partial is None:
                            partial_json = _canonical_json(partial)
                            if len(partial_json) > MAX_AGGREGATE_JSON_LENGTH:
                                raise ValueError(
                                    "Batch aggregate exceeds 10000 characters"
                                )
                            result_checksum = hashlib.sha256(
                                partial_json.encode("utf-8")
                            ).hexdigest()
                            batch_table.update_row(
                                {
                                    "ROWID": batch_row["ROWID"],
                                    "status": "COMPLETED",
                                    "processed_record_count": partial["recordCount"],
                                    "partial_aggregate_json": partial_json,
                                    "input_checksum": bulk_row["source_file_checksum"],
                                    "result_checksum": result_checksum,
                                    "completed_at": _catalyst_datetime_now(),
                                    "controlled_error_code": "",
                                }
                            )
                        if owner_field_available:
                            _persist_batch_owners(
                                app,
                                scan_row,
                                module_row,
                                batch_row,
                                bulk_row["source_file_checksum"],
                                owner_partials,
                            )
                        for finding in record_findings:
                            finding_summary["affectedRecordCount"] += 1
                            finding_summary["issueCount"] += len(finding["issues"])
                            finding_summary["missingIssueCount"] += finding["missingCount"]
                            finding_summary["invalidIssueCount"] += finding["invalidCount"]
                            for issue in finding["issues"]:
                                group_key = (
                                    issue["fieldApiName"],
                                    issue["issueType"],
                                    issue["importance"],
                                )
                                group = finding_summary["issueGroups"].setdefault(
                                    group_key,
                                    {
                                        "fieldApiName": issue["fieldApiName"],
                                        "fieldLabel": issue["fieldLabel"],
                                        "issueType": issue["issueType"],
                                        "severity": issue["severity"],
                                        "importance": issue["importance"],
                                        "recordCount": 0,
                                    },
                                )
                                group["recordCount"] += 1
                                if SEVERITY_RANK.get(issue["severity"], 1) > SEVERITY_RANK.get(
                                    group["severity"], 1
                                ):
                                    group["severity"] = issue["severity"]

                        stored_findings = record_findings[:remaining_finding_samples]
                        _persist_record_findings(
                            app,
                            scan_row,
                            module_row,
                            batch_row,
                            bulk_row["source_file_checksum"],
                            stored_findings,
                        )
                        finding_summary["storedSampleCount"] += len(stored_findings)
                        remaining_finding_samples -= len(stored_findings)
                        partials.append(partial)

                    try:
                        next(reader)
                    except StopIteration:
                        pass
                    else:
                        raise ValueError("Export contains more records than planned")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    if records_seen != expected_count:
        raise ValueError("Processed record count does not match provider count")
    aggregate = _merge_partials(partials, field_names)
    if aggregate["recordCount"] != expected_count:
        raise ValueError("Aggregated record count does not match provider count")
    result = _persist_results(
        app,
        scan_row,
        module_row,
        bulk_row,
        aggregate,
        field_names,
        _domain_payload(domain_accumulator),
    )
    record_summary_created = _persist_record_finding_summary(
        app, scan_row, module_row, bulk_row, finding_summary
    )
    owner_result = {"resultCount": 0, "createdResultCount": 0}
    if "Owner" in field_names:
        owner_rows = zcql.execute_query(
            "select * from owner_batch_aggregates where "
            f"scan_module_row_id = {module_row_id}"
        )
        owners = _merge_owner_rows(
            [item["owner_batch_aggregates"] for item in owner_rows],
            {str(row["ROWID"]) for row in batch_rows},
        )
        owner_result = _persist_owner_results(
            app, scan_row, module_row, bulk_row, owners
        )

    datastore.table("bulk_read_jobs").update_row(
        {
            "ROWID": bulk_row["ROWID"],
            "status": "PROCESSED",
            "controlled_error_code": "",
        }
    )
    datastore.table("scan_module_runs").update_row(
        {
            "ROWID": module_row["ROWID"],
            "status": "COMPLETED",
            "batches_completed": len(batch_rows),
            "records_processed": expected_count,
        }
    )

    module_results = zcql.execute_query(
        f"select * from scan_module_runs where scan_row_id = {scan_row_id}"
    )
    completed_count = sum(
        1
        for item in module_results
        if item["scan_module_runs"].get("status") == "COMPLETED"
        or item["scan_module_runs"]["ROWID"] == module_row["ROWID"]
    )
    scan_update = {
        "ROWID": scan_row["ROWID"],
        "completed_module_count": completed_count,
    }
    if completed_count == len(module_results):
        scan_update["status"] = "COMPLETED"
        scan_update["completed_at"] = _catalyst_datetime_now()
    datastore.table("scan_jobs").update_row(scan_update)

    return {
        "recordCount": expected_count,
        "batchCount": len(batch_rows),
        **result,
        "recordFindingCount": finding_summary["affectedRecordCount"],
        "recordIssueCount": finding_summary["issueCount"],
        "recordFindingSummaryCreated": record_summary_created,
        "ownerResultCount": owner_result["resultCount"],
        "createdOwnerResultCount": owner_result["createdResultCount"],
    }
