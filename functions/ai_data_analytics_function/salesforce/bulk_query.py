"""Salesforce Bulk API 2.0 Query submit + status poll.

This module is independent of Zoho Bulk Read. Do not import bulk_read or
zoho.client here. Results download and File Store are not implemented.

Schema (Catalyst Data Store; create the column in the console — this repo has
no table-migration mechanism):

    bulk_read_jobs.provider_job_id  text  Salesforce Query job id (750...)

Never write a Salesforce job id into zoho_job_id. Existing Zoho rows keep
using zoho_job_id. Missing provider_job_id means the row is not a Salesforce
query job.

Endpoints (API version stays in sync with salesforce.client):

    POST {instance_url}/services/data/v62.0/jobs/query
    GET  {instance_url}/services/data/v62.0/jobs/query/{jobId}

SOQL is built only from a stored field plan + scan window. Arbitrary raw SOQL
from a client is not accepted.
"""

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import quote, urlparse

import requests

from salesforce.client import SALESFORCE_API_VERSION
from salesforce.describe import is_safe_sobject_api_name

logger = logging.getLogger(__name__)

SALESFORCE_QUERY_CLOCK_FIELDS = frozenset({"CreatedDate", "LastModifiedDate"})
SALESFORCE_QUERY_JOB_STATES = frozenset(
    {"UploadComplete", "InProgress", "JobComplete", "Aborted", "Failed"}
)
_PROVIDER_JOB_ID = re.compile(r"^[a-zA-Z0-9]{15,18}$")

# Existing extract-job statuses. JobComplete is READY_TO_DOWNLOAD because
# CSV download is a later increment.
_STATE_TO_INTERNAL = {
    "UploadComplete": "SUBMITTED",
    "InProgress": "PROCESSING",
    "JobComplete": "READY_TO_DOWNLOAD",
    "Aborted": "FAILED_TERMINAL",
    "Failed": "FAILED_TERMINAL",
}


class SalesforceBulkError(RuntimeError):
    """Controlled Salesforce Bulk API failure. Message must never include tokens."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def is_safe_salesforce_soql_identifier(value: str) -> bool:
    """Object and field API names only; no dots, quotes, or SOQL fragments."""
    return is_safe_sobject_api_name(str(value or "").strip())


def to_salesforce_soql_datetime(value) -> str:
    """UTC SOQL DateTime literal. Seconds precision; Z suffix; not Zoho ISO offset."""
    return _as_utc_datetime(value).strftime("%Y-%m-%dT%H:%M:%SZ")


def salesforce_query_jobs_url(instance_url: str, job_id=None) -> str:
    parsed = urlparse(str(instance_url or "").strip().rstrip("/"))
    if parsed.scheme != "https" or not parsed.netloc:
        raise SalesforceBulkError(
            "SALESFORCE_INSTANCE_MISSING",
            "Salesforce instance URL is unavailable",
        )
    base = (
        f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"
        f"/services/data/{SALESFORCE_API_VERSION}/jobs/query"
    )
    if job_id is None:
        return base
    job_id = str(job_id or "").strip()
    if not _PROVIDER_JOB_ID.fullmatch(job_id):
        raise SalesforceBulkError(
            "INVALID_JOB_ID", "Salesforce Bulk job id is invalid"
        )
    return f"{base}/{quote(job_id, safe='')}"


def build_salesforce_query_soql(
    object_api_name,
    field_names,
    clock_field,
    from_utc,
    to_utc,
):
    """Build a bounded query from a Salesforce field plan. No raw SOQL input."""
    object_name = _require_identifier(object_api_name, "INVALID_OBJECT_API_NAME")
    fields = _normalized_field_list(field_names)
    clock = _require_identifier(clock_field, "INVALID_FIELD_API_NAME")
    if clock not in SALESFORCE_QUERY_CLOCK_FIELDS:
        raise SalesforceBulkError(
            "INVALID_CLOCK_FIELD",
            "Salesforce clock field must be CreatedDate or LastModifiedDate",
        )
    if clock not in fields:
        raise SalesforceBulkError(
            "CLOCK_FIELD_UNAVAILABLE",
            "The Salesforce field plan does not include the scan clock field",
        )
    if to_utc in (None, ""):
        raise SalesforceBulkError(
            "INVALID_SCAN_WINDOW", "The stored scan window is invalid"
        )

    select_list = ",".join(fields)
    where = [f"{clock} < {to_salesforce_soql_datetime(to_utc)}"]
    if from_utc not in (None, ""):
        where.insert(0, f"{clock} >= {to_salesforce_soql_datetime(from_utc)}")
    return f"SELECT {select_list} FROM {object_name} WHERE {' AND '.join(where)}"


def build_salesforce_query_soql_from_plan(scan_row, module_row):
    """SOQL from persisted scan_jobs + scan_module_runs field plan."""
    try:
        fields = json.loads((module_row or {}).get("field_allowlist_json") or "[]")
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SalesforceBulkError(
            "INVALID_FIELD_PLAN", "The stored Salesforce field allowlist is invalid"
        ) from exc
    return build_salesforce_query_soql(
        (module_row or {}).get("module_api_name"),
        fields,
        (scan_row or {}).get("clock_field"),
        (scan_row or {}).get("from_utc"),
        (scan_row or {}).get("to_utc"),
    )


def normalize_salesforce_query_job(payload: dict) -> dict:
    """Map a Bulk API 2.0 Query job resource onto the extract-job model."""
    if not isinstance(payload, dict):
        raise SalesforceBulkError(
            "SALESFORCE_JOB_RESPONSE_INVALID",
            "Salesforce returned an unrecognized Bulk query job",
        )
    job_id = str(payload.get("id") or "").strip()
    if not _PROVIDER_JOB_ID.fullmatch(job_id):
        raise SalesforceBulkError(
            "SALESFORCE_JOB_RESPONSE_INVALID",
            "Salesforce returned an unrecognized Bulk query job",
        )
    state = str(payload.get("state") or "").strip()
    if state not in SALESFORCE_QUERY_JOB_STATES:
        raise SalesforceBulkError(
            "SALESFORCE_JOB_STATE_UNKNOWN",
            "Salesforce returned an unrecognized Bulk query job state",
        )
    processed = _optional_int(payload.get("numberRecordsProcessed"))
    failed = _optional_int(payload.get("numberRecordsFailed"))
    total_size = _optional_int(
        payload.get("totalSize")
        if payload.get("totalSize") not in (None, "")
        else payload.get("contentLength")
    )
    locator = payload.get("locator")
    locator_text = str(locator).strip() if locator not in (None, "") else None
    return {
        "id": job_id,
        "state": state,
        "internalStatus": _STATE_TO_INTERNAL[state],
        "object": str(payload.get("object") or "").strip() or None,
        "operation": str(payload.get("operation") or "").strip() or None,
        "numberRecordsProcessed": processed,
        "numberRecordsFailed": failed,
        "totalSize": total_size,
        "locator": locator_text,
        "resultsAvailable": state == "JobComplete",
        "locatorAvailable": bool(locator_text),
    }


def persist_salesforce_query_job(datastore, job: dict, bulk_row=None):
    """Store provider_job_id on bulk_read_jobs. Never writes zoho_job_id."""
    if not isinstance(job, dict) or not job.get("id"):
        raise SalesforceBulkError(
            "SALESFORCE_JOB_RESPONSE_INVALID",
            "Salesforce returned an unrecognized Bulk query job",
        )
    table = datastore.table("bulk_read_jobs")
    row = {
        "provider_job_id": job["id"],
        "status": job.get("internalStatus") or _STATE_TO_INTERNAL.get(job.get("state")),
    }
    if job.get("numberRecordsProcessed") is not None:
        row["provider_record_count"] = job["numberRecordsProcessed"]
    bulk_row = bulk_row or {}
    if bulk_row.get("ROWID"):
        row["ROWID"] = bulk_row["ROWID"]
        table.update_row(row)
        return row
    row["bulk_job_id"] = str(bulk_row.get("bulk_job_id") or f"bulk_{uuid.uuid4().hex}")
    row["provider_page"] = 1
    row["attempt_count"] = int(bulk_row.get("attempt_count") or 0) or 1
    if bulk_row.get("scan_module_row_id") is not None:
        row["scan_module_row_id"] = bulk_row["scan_module_row_id"]
    return table.insert_row(row)


def submit_salesforce_query_job(
    datastore,
    connection_row,
    object_api_name,
    field_names,
    clock_field,
    from_utc,
    to_utc,
    bulk_row=None,
):
    """POST a Bulk API 2.0 Query job using the stored connection token."""
    soql = build_salesforce_query_soql(
        object_api_name, field_names, clock_field, from_utc, to_utc
    )
    access_token, instance_url = _stored_access_token(datastore, connection_row)
    url = salesforce_query_jobs_url(instance_url)
    payload = _authorized_json(
        "POST",
        url,
        access_token,
        json_body={"operation": "query", "query": soql},
        timeout=30,
    )
    job = normalize_salesforce_query_job(payload)
    if bulk_row is not None:
        persist_salesforce_query_job(datastore, job, bulk_row=bulk_row)
    return job


def poll_salesforce_query_job(
    datastore, connection_row, provider_job_id, bulk_row=None
):
    """GET a Bulk API 2.0 Query job. Does not download results."""
    access_token, instance_url = _stored_access_token(datastore, connection_row)
    url = salesforce_query_jobs_url(instance_url, provider_job_id)
    payload = _authorized_json("GET", url, access_token, timeout=20)
    job = normalize_salesforce_query_job(payload)
    if str(job["id"]) != str(provider_job_id).strip():
        raise SalesforceBulkError(
            "SALESFORCE_JOB_RESPONSE_INVALID",
            "Salesforce returned a different Bulk query job",
        )
    if bulk_row is not None:
        persist_salesforce_query_job(datastore, job, bulk_row=bulk_row)
    return job


def _stored_access_token(datastore, connection_row):
    from salesforce.client import get_salesforce_access_token

    try:
        return get_salesforce_access_token(datastore, connection_row)
    except Exception as exc:
        code = getattr(exc, "code", None)
        if code:
            raise SalesforceBulkError(code, str(exc)) from exc
        logger.warning("Salesforce token refresh failed: %s", type(exc).__name__)
        raise SalesforceBulkError(
            "TOKEN_REFRESH_FAILED", "Salesforce token refresh failed"
        ) from exc


def _require_identifier(value, code):
    name = str(value or "").strip()
    if not is_safe_salesforce_soql_identifier(name):
        raise SalesforceBulkError(code, "Salesforce identifier is invalid")
    return name


def _normalized_field_list(field_names):
    if not isinstance(field_names, (list, tuple)) or not field_names:
        raise SalesforceBulkError(
            "INVALID_FIELD_PLAN", "The stored Salesforce field allowlist is invalid"
        )
    fields = []
    seen = set()
    for raw in field_names:
        name = _require_identifier(raw, "INVALID_FIELD_API_NAME")
        if name in seen:
            continue
        seen.add(name)
        fields.append(name)
    if not fields:
        raise SalesforceBulkError(
            "INVALID_FIELD_PLAN", "The stored Salesforce field allowlist is invalid"
        )
    return fields


def _as_utc_datetime(value) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text = str(value or "").strip()
    if not text:
        raise SalesforceBulkError(
            "INVALID_SCAN_WINDOW", "The stored scan window is invalid"
        )
    for date_format in (
        "%Y-%m-%d %H:%M:%S:%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
    ):
        try:
            return datetime.strptime(text, date_format).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SalesforceBulkError(
            "INVALID_SCAN_WINDOW", "The stored scan window is invalid"
        ) from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _optional_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _error_code_from_response(response):
    try:
        payload = response.json()
    except ValueError:
        return None
    if isinstance(payload, list) and payload:
        first = payload[0] if isinstance(payload[0], dict) else {}
        return str(first.get("errorCode") or first.get("error") or "").strip() or None
    if isinstance(payload, dict):
        return (
            str(payload.get("errorCode") or payload.get("error") or "").strip() or None
        )
    return None


def _map_http_error(status, error_code):
    if status in {401, 403}:
        return "TOKEN_REFRESH_FAILED", "Salesforce token refresh failed"
    if error_code in {"MALFORMED_QUERY", "INVALID_QUERY_FILTER_OPERATOR"}:
        return "INVALID_SOQL", "Salesforce rejected the generated query"
    if error_code in {"INVALID_FIELD", "INVALID_FIELD_FOR_INSERT_UPDATE"}:
        return "INVALID_FIELD_API_NAME", "Salesforce identifier is invalid"
    if error_code in {"INVALID_TYPE", "NOT_FOUND"}:
        return "INVALID_OBJECT_API_NAME", "Salesforce identifier is invalid"
    if error_code:
        return "SALESFORCE_BULK_QUERY_FAILED", "Salesforce rejected the Bulk query job"
    if 400 <= status < 500:
        return "SALESFORCE_BULK_QUERY_FAILED", "Salesforce rejected the Bulk query job"
    return "SALESFORCE_BULK_QUERY_FAILED", "Salesforce Bulk query request failed"


def _authorized_json(method, url, access_token, json_body=None, timeout=20):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    try:
        if method == "POST":
            headers["Content-Type"] = "application/json"
            response = requests.post(
                url, headers=headers, json=json_body, timeout=timeout
            )
        else:
            response = requests.get(url, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        logger.warning(
            "Salesforce bulk query request failed: %s", type(exc).__name__
        )
        raise SalesforceBulkError(
            "SALESFORCE_BULK_QUERY_FAILED",
            "Salesforce Bulk query request failed",
        ) from exc

    if not response.ok:
        error_code = _error_code_from_response(response)
        logger.warning(
            "Salesforce bulk query request failed: status=%s errorCode=%s",
            response.status_code,
            error_code or "",
        )
        mapped_code, message = _map_http_error(response.status_code, error_code)
        raise SalesforceBulkError(mapped_code, message)

    try:
        payload = response.json()
    except ValueError as exc:
        raise SalesforceBulkError(
            "SALESFORCE_JOB_RESPONSE_INVALID",
            "Salesforce returned an unrecognized Bulk query job",
        ) from exc
    return payload
