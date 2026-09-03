"""Shared constants, validation, hashing, response, and date helpers."""

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from flask import Request, make_response
import zcatalyst_sdk

logger = logging.getLogger(__name__)

STATE_TTL_MINUTES = 10
ZOHO_SCOPE = "ZohoCRM.settings.modules.READ,ZohoCRM.modules.READ,ZohoCRM.users.READ,ZohoCRM.settings.workflow_rules.READ,ZohoCRM.settings.layouts.READ,ZohoSearch.securesearch.READ,ZohoCRM.bulk.read,ZohoCRM.settings.fields.READ,ZohoCRM.org.READ"
SCAN_DEPTHS = frozenset({"quick", "presales", "deep", "full"})
SCAN_CLOCK_FIELDS = {"created": "Created_Time", "modified": "Modified_Time"}
ROLLING_RANGE_DAYS = {"7d": 7, "30d": 30, "90d": 90}
BASE_FIELD_ALLOWLIST = ("id", "Created_Time", "Modified_Time")
QUALITY_FIELD_CANDIDATES = frozenset(
    {
        "First_Name",
        "Last_Name",
        "Company",
        "Account_Name",
        "Deal_Name",
        "Email",
        "Secondary_Email",
        "Phone",
        "Mobile",
        "Website",
        "Industry",
        "Lead_Source",
        "Lead_Status",
        "Stage",
        "Pipeline",
        "Amount",
        "Closing_Date",
        "Billing_Country",
        "Mailing_Country",
        "Country",
        "Annual_Revenue",
        "Employees",
        "Created_By",
        "Owner",
    }
)
API_VERSION = "v6"
RULE_VERSION = "rules-v1"
FIELD_PLAN_VERSION = "base-fields-v1"
DISCOVERED_FIELD_PLAN_VERSION = "metadata-fields-v2"
MAX_FILESTORE_UPLOAD_BYTES = 100 * 1024 * 1024
MAX_BULK_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024

class AuthenticationRequired(RuntimeError):
    """Raised when a route has no authenticated Catalyst application user."""


def get_current_user() -> dict:
    """Return the SDK-verified user for the current Catalyst invocation."""
    try:
        user = zcatalyst_sdk.initialize().authentication().get_current_user()
    except Exception as exc:  # noqa: BLE001 - normalize SDK auth failures
        raise AuthenticationRequired("Catalyst authentication is required") from exc
    if not isinstance(user, dict) or not user.get("user_id"):
        raise AuthenticationRequired("Catalyst authentication is required")
    if str(user.get("status") or "ACTIVE").upper() != "ACTIVE":
        raise AuthenticationRequired("The Catalyst user is not active")
    return user


def get_current_user_id(request: Request = None) -> str:
    """Return the authenticated Catalyst user ID; never trust request headers."""
    del request
    return str(get_current_user()["user_id"])

def to_catalyst_datetime(dt: datetime) -> str:
    """Catalyst Data Store's DateTime columns expect this exact shape -
    confirmed against Catalyst's own docs, which show existing columns
    rendered as e.g. "2021-08-17 13:02:11:184": space-separated,
    milliseconds after a colon, no timezone suffix. Not ISO 8601."""
    return dt.strftime("%Y-%m-%d %H:%M:%S:%f")[:-3]


def from_catalyst_datetime(s: str) -> datetime:
    for date_format in ("%Y-%m-%d %H:%M:%S:%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, date_format).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError("Unsupported Catalyst DateTime value")


def to_catalyst_column_datetime(dt: datetime) -> str:
    """Format a custom Data Store DateTime column for an insert/update."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def to_zoho_datetime(value: str) -> str:
    """Convert a stored UTC scan boundary to Zoho's ISO-8601 format.

    Bulk Read accepts DateTime criteria without milliseconds. Keeping the UTC
    offset explicit also prevents the organization timezone from changing the
    meaning of an already-persisted scan window.
    """
    return from_catalyst_datetime(value).isoformat(timespec="seconds")


def with_fragment_parameter(url: str, key: str, value: str) -> str:
    """Add an OAuth result marker that Catalyst will not receive or validate."""
    parts = urlsplit(url)
    fragment = dict(parse_qsl(parts.fragment, keep_blank_values=True))
    fragment[key] = value
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, urlencode(fragment)))


def json_response(payload, status=200):
    return make_response(
        json.dumps(payload), status, {"Content-Type": "application/json"}
    )


def canonical_hash(value) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def resolve_scan_window(range_config: dict, now_utc: datetime):
    range_id = range_config.get("id") if isinstance(range_config, dict) else None
    if range_id in ROLLING_RANGE_DAYS:
        return now_utc - timedelta(days=ROLLING_RANGE_DAYS[range_id]), now_utc
    if range_id == "all":
        return None, now_utc
    if range_id in {"qtr", "fy"}:
        raise ValueError(
            "Quarter and fiscal-year ranges require authoritative organization calendar metadata"
        )
    raise ValueError("Unsupported date range")


def validate_scan_config(payload: dict, connection_row: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("The request body must be a JSON object")

    modules = payload.get("modules")
    if not isinstance(modules, list) or not modules:
        raise ValueError("Select at least one module")
    if not all(isinstance(module, str) and module for module in modules):
        raise ValueError("Every module must be a non-empty API name")
    if len(set(modules)) != len(modules):
        raise ValueError("Duplicate modules are not allowed")

    accessible_modules = json.loads(connection_row.get("accessible_modules") or "[]")
    accessible_names = {
        module.get("apiName")
        for module in accessible_modules
        if isinstance(module, dict) and module.get("apiName")
    }
    unauthorized = sorted(set(modules) - accessible_names)
    if unauthorized:
        raise PermissionError(
            f"Modules are not accessible to this connection: {', '.join(unauthorized)}"
        )

    depth = payload.get("depth")
    if depth not in SCAN_DEPTHS:
        raise ValueError("Unsupported scan depth")

    clock = payload.get("clock")
    if clock not in SCAN_CLOCK_FIELDS:
        raise ValueError("Clock must be 'created' or 'modified'")

    now_utc = datetime.now(timezone.utc)
    from_utc, to_utc = resolve_scan_window(payload.get("range"), now_utc)
    return {
        "modules": modules,
        "depth": depth,
        "clock_field": SCAN_CLOCK_FIELDS[clock],
        "range_id": payload["range"]["id"],
        "from_utc": from_utc,
        "to_utc": to_utc,
    }

class DiscoveryError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code

def foreign_row_id(value):
    if isinstance(value, dict):
        return value.get("ROWID") or value.get("rowid")
    return value


def query_list_values(request: Request, name: str, max_count=50):
    """Read a list filter through Catalyst without relying on duplicate keys.

    Catalyst may collapse repeated query parameters to their last value. The
    client therefore sends the plural form as one comma-separated value, while
    this parser continues accepting the older repeated singular form.
    """
    values = []
    seen = set()
    for key in (name, f"{name}s"):
        for raw_value in request.args.getlist(key):
            for part in str(raw_value or "").split(","):
                candidate = part.strip()
                if candidate and candidate not in seen:
                    seen.add(candidate)
                    values.append(candidate)
                    if len(values) >= max_count:
                        return values
    return values
