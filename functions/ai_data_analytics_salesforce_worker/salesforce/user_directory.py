"""Salesforce owner directory: Users and Groups/Queues.

Persistence table (Catalyst Data Store; create in the console — this repo has
no table-migration mechanism):

    salesforce_connection_owners

Columns:
    directory_id        text
    directory_key       text   unique per connection + Salesforce Id
    connection_row_id   text/foreign  (salesforce_connections.ROWID)
    crm_user_id         text   18-character Salesforce Id (15 stored as-is)
    display_name        text
    email               text
    username            text
    active              boolean
    owner_type          text   user | queue | group
    synced_at           datetime

Do not write to zoho_connection_users.

Worker copy: also lives in ai_data_analytics_salesforce_worker/salesforce/user_directory.py.

15→18 character Ids: Salesforce REST/SOQL normally returns 18-character Ids.
This module does not convert 15-character Ids; it stores the value returned.
"""

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

SALESFORCE_DIRECTORY_TABLE = "salesforce_connection_owners"
SALESFORCE_USER_QUERY = "SELECT Id, Name, Email, IsActive, Username FROM User"
SALESFORCE_USER_QUERIES = (
    SALESFORCE_USER_QUERY,
    "SELECT Id, Name, IsActive FROM User",
    "SELECT Id, Name FROM User",
)
SALESFORCE_GROUP_QUERY = (
    "SELECT Id, Name, Type, Email FROM Group WHERE Type IN ('Queue', 'Regular')"
)
SALESFORCE_GROUP_QUERIES = (
    SALESFORCE_GROUP_QUERY,
    "SELECT Id, Name, Type FROM Group WHERE Type IN ('Queue', 'Regular')",
)
MAX_QUERY_PAGES = 50
_SALESFORCE_ID = re.compile(r"^[a-zA-Z0-9]{15}(?:[a-zA-Z0-9]{3})?$")
_GROUP_TYPE_MAP = {"Queue": "queue", "Regular": "group"}


def is_salesforce_record_id(value: str) -> bool:
    return bool(value and _SALESFORCE_ID.fullmatch(value))


def _is_true(value):
    if value is True or value is False:
        return value is True
    return str(value or "").strip().lower() in {"true", "1", "yes", "t"}


def _connection_row_id(connection_row):
    """Match Zoho's foreign_row_id unwrap of Catalyst ROWID values."""
    value = (connection_row or {}).get("ROWID")
    if isinstance(value, dict):
        value = value.get("ROWID") or value.get("rowid")
    return str(value or "").strip()


def _trimmed(value, limit=255):
    return str(value or "").strip()[:limit]


def _synced_at(now=None):
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def salesforce_directory_key(connection_row_id: str, crm_user_id: str) -> str:
    return f"{connection_row_id}:{crm_user_id}"


def normalize_salesforce_user(record: dict):
    """Map a User sObject row to a Salesforce-native directory entry."""
    if not isinstance(record, dict):
        return None
    crm_user_id = str(record.get("Id") or "").strip()
    if not is_salesforce_record_id(crm_user_id):
        return None
    display_name = _trimmed(record.get("Name")) or "Unknown user"
    if "IsActive" in record:
        active = _is_true(record.get("IsActive"))
    else:
        active = True
    return {
        "crmUserId": crm_user_id,
        "displayName": display_name,
        "email": _trimmed(record.get("Email")),
        "username": _trimmed(record.get("Username")),
        "active": active,
        "type": "user",
    }


def normalize_salesforce_group(record: dict):
    """Map a Group sObject row; Queue vs Regular becomes queue | group."""
    if not isinstance(record, dict):
        return None
    crm_user_id = str(record.get("Id") or "").strip()
    if not is_salesforce_record_id(crm_user_id):
        return None
    owner_type = _GROUP_TYPE_MAP.get(str(record.get("Type") or "").strip())
    if not owner_type:
        return None
    fallback = "Unknown queue" if owner_type == "queue" else "Unknown group"
    display_name = _trimmed(record.get("Name")) or fallback
    return {
        "crmUserId": crm_user_id,
        "displayName": display_name,
        "email": _trimmed(record.get("Email")),
        "username": "",
        "active": True,
        "type": owner_type,
    }


def build_salesforce_directory_row(connection_row_id: str, entry: dict, synced_at: str):
    crm_user_id = str(entry.get("crmUserId") or "").strip()
    return {
        "directory_id": f"sfdir_{connection_row_id}_{crm_user_id}"[:100],
        "directory_key": salesforce_directory_key(connection_row_id, crm_user_id),
        "connection_row_id": connection_row_id,
        "crm_user_id": crm_user_id,
        "display_name": _trimmed(entry.get("displayName")) or "Unknown owner",
        "email": _trimmed(entry.get("email")),
        "username": _trimmed(entry.get("username")),
        "active": _is_true(entry.get("active")),
        "owner_type": str(entry.get("type") or "").strip(),
        "synced_at": synced_at,
    }


def upsert_salesforce_directory_entries(
    table,
    existing_rows: list,
    entries: list,
    connection_row_id: str,
    synced_at: str,
    managed_types=None,
):
    """Insert or update directory rows. Missing identities are marked inactive."""
    existing_by_key = {}
    for row in existing_rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("directory_key") or "").strip()
        if key:
            existing_by_key[key] = row

    seen = set()
    inserted = 0
    updated = 0
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("crmUserId"):
            continue
        if managed_types is not None and entry.get("type") not in managed_types:
            continue
        row_data = build_salesforce_directory_row(
            connection_row_id, entry, synced_at
        )
        key = row_data["directory_key"]
        if key in seen:
            continue
        seen.add(key)
        existing = existing_by_key.get(key)
        try:
            if existing:
                row_data["ROWID"] = existing["ROWID"]
                table.update_row(row_data)
                updated += 1
            else:
                table.insert_row(row_data)
                inserted += 1
        except Exception:  # noqa: BLE001 - keep other owners even if one row fails
            logger.exception(
                "Could not persist Salesforce owner directory row directory_key=%s",
                key,
            )

    inactivated = 0
    for key, row in existing_by_key.items():
        if key in seen:
            continue
        if managed_types is not None and str(row.get("owner_type") or "") not in managed_types:
            continue
        if not _is_true(row.get("active")):
            continue
        table.update_row(
            {
                "ROWID": row["ROWID"],
                "active": False,
                "synced_at": synced_at,
            }
        )
        inactivated += 1

    return {
        "inserted": inserted,
        "updated": updated,
        "inactivated": inactivated,
        "seen": len(seen),
    }


def _salesforce_authorized_get(url, access_token, params=None, timeout=30):
    from salesforce.client import _authorized_get

    return _authorized_get(url, access_token, params=params, timeout=timeout)


def _absolute_next_records_url(instance_url: str, next_records_url: str) -> str:
    value = str(next_records_url or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme == "https" and parsed.netloc:
        return value
    if value.startswith("/"):
        return f"{instance_url.rstrip('/')}{value}"
    return ""


def fetch_salesforce_soql_records(access_token: str, instance_url: str, soql: str):
    """Run SOQL and follow nextRecordsUrl. Uses the stored-connection access token."""
    from salesforce.client import SALESFORCE_API_VERSION

    records = []
    url = f"{instance_url.rstrip('/')}/services/data/{SALESFORCE_API_VERSION}/query"
    params = {"q": soql}
    pages = 0
    while url:
        pages += 1
        if pages > MAX_QUERY_PAGES:
            raise requests.RequestException("Salesforce directory query exceeded page limit")
        payload = _salesforce_authorized_get(
            url, access_token, params=params, timeout=30
        )
        params = None
        if not isinstance(payload, dict):
            raise ValueError("Salesforce directory response was invalid")
        batch = payload.get("records") or []
        if not isinstance(batch, list):
            raise ValueError("Salesforce directory response was invalid")
        records.extend(item for item in batch if isinstance(item, dict))
        if payload.get("done") is True:
            break
        url = _absolute_next_records_url(instance_url, payload.get("nextRecordsUrl") or "")
        if not url:
            break
    return records, pages


def _fetch_soql_with_fallback(access_token: str, instance_url: str, queries):
    last_error = None
    for soql in queries:
        try:
            return fetch_salesforce_soql_records(access_token, instance_url, soql)
        except (requests.RequestException, ValueError, TypeError) as exc:
            logger.warning(
                "Salesforce directory query failed (%s); retrying with a narrower field list",
                type(exc).__name__,
            )
            last_error = exc
    if last_error is None:
        raise ValueError("Salesforce directory query is not configured")
    raise last_error


def fetch_salesforce_users(access_token: str, instance_url: str):
    records, pages = _fetch_soql_with_fallback(
        access_token, instance_url, SALESFORCE_USER_QUERIES
    )
    entries = []
    for record in records:
        entry = normalize_salesforce_user(record)
        if entry:
            entries.append(entry)
    return entries, pages


def fetch_salesforce_groups(access_token: str, instance_url: str):
    records, pages = _fetch_soql_with_fallback(
        access_token, instance_url, SALESFORCE_GROUP_QUERIES
    )
    entries = []
    for record in records:
        entry = normalize_salesforce_group(record)
        if entry:
            entries.append(entry)
    return entries, pages


def _load_existing_directory_rows(zcql, connection_row_id: str):
    results = zcql.execute_query(
        f"select * from {SALESFORCE_DIRECTORY_TABLE} where "
        f"connection_row_id = {connection_row_id}"
    )
    rows = []
    for item in results or []:
        if not isinstance(item, dict):
            continue
        row = item.get(SALESFORCE_DIRECTORY_TABLE)
        if not isinstance(row, dict) and len(item) == 1:
            candidate = next(iter(item.values()))
            row = candidate if isinstance(candidate, dict) else None
        if isinstance(row, dict):
            rows.append(row)
    return rows


def sync_salesforce_owner_directory(
    datastore, zcql, connection_row: dict, access_token: str, instance_url: str, now=None
):
    """Fetch Users + Groups/Queues and upsert into salesforce_connection_owners."""
    connection_row_id = _connection_row_id(connection_row)
    if not connection_row_id.isdigit():
        return {
            "refreshed": False,
            "apiCalls": 0,
            "counts": {"user": 0, "queue": 0, "group": 0},
            "warning": "Connection identifier is invalid for directory caching",
        }

    warnings = []
    try:
        existing_rows = _load_existing_directory_rows(zcql, connection_row_id)
    except Exception as exc:  # noqa: BLE001 - still fetch and insert when cache read fails
        logger.exception("Could not read Salesforce owner directory cache: %s", exc)
        existing_rows = []
        warnings.append("Salesforce owner directory cache could not be read")

    api_calls = 0
    fetched = []
    managed_types = set()

    try:
        users, user_pages = fetch_salesforce_users(access_token, instance_url)
        api_calls += user_pages
        fetched.extend(users)
        managed_types.add("user")
    except (requests.RequestException, ValueError, TypeError) as exc:
        logger.warning(
            "Salesforce User directory request failed: %s", type(exc).__name__
        )
        warnings.append("Salesforce User directory request failed")

    try:
        groups, group_pages = fetch_salesforce_groups(access_token, instance_url)
        api_calls += group_pages
        fetched.extend(groups)
        managed_types.update({"queue", "group"})
    except (requests.RequestException, ValueError, TypeError) as exc:
        logger.warning(
            "Salesforce Group directory request failed: %s", type(exc).__name__
        )
        warnings.append("Salesforce Group directory request failed")

    if not managed_types:
        return {
            "refreshed": False,
            "apiCalls": api_calls,
            "counts": {"user": 0, "queue": 0, "group": 0},
            "warning": warnings[0] if warnings else "Salesforce owner directory request failed",
        }

    synced_at = _synced_at(now)
    persist = {"inserted": 0, "updated": 0, "inactivated": 0, "seen": 0}
    try:
        table = datastore.table(SALESFORCE_DIRECTORY_TABLE)
        persist = upsert_salesforce_directory_entries(
            table,
            existing_rows,
            fetched,
            connection_row_id,
            synced_at,
            managed_types=managed_types,
        )
    except Exception as exc:  # noqa: BLE001 - keep discovery usable without cache
        logger.exception("Could not persist Salesforce owner directory cache: %s", exc)
        return {
            "refreshed": False,
            "apiCalls": api_calls,
            "counts": {"user": 0, "queue": 0, "group": 0},
            "warning": "Salesforce owner directory cache could not be stored",
        }

    counts = {"user": 0, "queue": 0, "group": 0}
    for entry in fetched:
        kind = entry.get("type")
        if kind in counts:
            counts[kind] += 1

    stored = int(persist.get("inserted") or 0) + int(persist.get("updated") or 0)
    if fetched and stored == 0:
        warnings.append("Salesforce owner directory cache could not be stored")
        return {
            "refreshed": False,
            "apiCalls": api_calls,
            "counts": counts,
            "warning": "; ".join(warnings),
        }

    return {
        "refreshed": stored > 0 or not fetched,
        "apiCalls": api_calls,
        "counts": counts,
        "warning": "; ".join(warnings) if warnings else None,
    }


def get_salesforce_owner_directory(request, datastore):
    import zcatalyst_sdk

    from common.core import DiscoveryError, get_current_user_id, json_response
    from salesforce.client import get_salesforce_access_token
    from salesforce.oauth import (
        find_active_salesforce_connection,
        find_connected_salesforce_connection,
    )

    user_id = get_current_user_id(request)
    zcql = zcatalyst_sdk.initialize().zcql()
    row = find_active_salesforce_connection(
        zcql, user_id
    ) or find_connected_salesforce_connection(zcql, user_id)
    if not row:
        return json_response(
            {
                "error": {
                    "code": "SALESFORCE_CONNECTION_REQUIRED",
                    "message": "Connect Salesforce CRM",
                }
            },
            409,
        )

    try:
        access_token, instance_url = get_salesforce_access_token(datastore, row)
        result = sync_salesforce_owner_directory(
            datastore, zcql, row, access_token, instance_url
        )
    except DiscoveryError as exc:
        logger.exception(
            "Salesforce owner directory failed for user %s with %s",
            user_id,
            exc.code,
        )
        return json_response(
            {"error": {"code": exc.code, "message": str(exc)}},
            502,
        )
    except Exception:  # noqa: BLE001 - keep provider details server-side
        logger.exception(
            "Unexpected Salesforce owner directory failure for user %s", user_id
        )
        return json_response(
            {
                "error": {
                    "code": "SALESFORCE_DIRECTORY_FAILED",
                    "message": "Salesforce owner directory could not be read",
                }
            },
            500,
        )

    if not result.get("refreshed") and result.get("warning"):
        status = (
            502
            if "could not be read" in str(result["warning"])
            or "request failed" in str(result["warning"])
            or "could not be stored" in str(result["warning"])
            else 200
        )
        if status == 502:
            return json_response(
                {
                    "error": {
                        "code": "DIRECTORY_DISCOVERY_FAILED",
                        "message": result["warning"],
                    }
                },
                502,
            )

    return json_response(
        {
            "connectionId": str(row["ROWID"]),
            "refreshed": result["refreshed"],
            "apiCalls": result["apiCalls"],
            "counts": result["counts"],
            "warning": result["warning"],
        }
    )
