"""Shared Salesforce owner identity and directory lookup.

Used by scan processing (Users / owner_quality) and by the Records export
reader so both surfaces resolve OwnerId the same way. One Users+Groups
directory sync, not one Salesforce call per record.
"""

import hashlib
import json
import logging

from salesforce.user_directory import (
    SALESFORCE_DIRECTORY_TABLE,
    is_salesforce_record_id,
    sync_salesforce_owner_directory,
)


LOGGER = logging.getLogger(__name__)
OWNER_FIELD_NAMES = ("Owner", "OwnerId")
SALESFORCE_CONNECTIONS_TABLE = "salesforce_connections"


def owner_field_name(names):
    """Return the planned owner field: Zoho Owner, else Salesforce OwnerId."""
    if names is None:
        return None
    for name in OWNER_FIELD_NAMES:
        if name in names:
            return name
    return None


def _canonical_hash(value):
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def crm_user_owner_key(crm_user_id):
    return _canonical_hash({"crm_user_id": crm_user_id})


def _is_true(value):
    if value is True or value is False:
        return value is True
    normalized = str(value or "").strip().lower()
    return normalized in {"true", "1", "yes", "t"}


def _row_id(value):
    if isinstance(value, dict):
        return str(value.get("ROWID") or value.get("rowid") or "").strip()
    return str(value or "").strip()


def _column(row, *names):
    by_case = {str(key).casefold(): value for key, value in (row or {}).items()}
    for name in names:
        if name.casefold() in by_case:
            return by_case[name.casefold()]
    return None


def _zcql_rows(results, table_name):
    rows = []
    for item in results or []:
        if not isinstance(item, dict):
            continue
        row = item.get(table_name)
        if not isinstance(row, dict) and len(item) == 1:
            candidate = next(iter(item.values()))
            row = candidate if isinstance(candidate, dict) else None
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _normalize_salesforce_id(value):
    return str(value or "").strip().strip('"').strip("'")


def directory_lookup_keys(crm_user_id):
    """Keys that must match Bulk CSV OwnerId to REST User/Group Id.

    Salesforce 15-character Ids are case-insensitive. The 18-character form
    adds a checksum; Bulk CSV and User SOQL can return either length or
    different casing for the same owner.
    """
    value = _normalize_salesforce_id(crm_user_id)
    keys = []
    if value:
        keys.append(crm_user_owner_key(value))
    if is_salesforce_record_id(value):
        prefix = value[:15]
        keys.append(crm_user_owner_key(prefix))
        keys.append(_canonical_hash({"crm_user_id": prefix.casefold()}))
    seen = []
    for key in keys:
        if key not in seen:
            seen.append(key)
    return seen


def lookup_owner_display_name(owner_id, owner_directory, fallback="Unknown owner"):
    if not owner_directory:
        return fallback
    for key in directory_lookup_keys(owner_id):
        name = owner_directory.get(key)
        if name:
            return name
    return fallback


def load_salesforce_connection_row(zcql, scan_row):
    connection_id = _row_id((scan_row or {}).get("connection_row_id"))
    if not connection_id.isdigit():
        return None
    try:
        results = zcql.execute_query(
            f"select * from {SALESFORCE_CONNECTIONS_TABLE} where "
            f"ROWID = {connection_id} limit 1"
        )
    except Exception as exc:  # noqa: BLE001 - connection lookup is optional for names
        LOGGER.warning("Could not read Salesforce connection for owner directory: %s", exc)
        return None
    for item in results or []:
        row = item.get(SALESFORCE_CONNECTIONS_TABLE) if isinstance(item, dict) else None
        if isinstance(row, dict):
            return row
    return None


def load_salesforce_owner_directory(zcql, connection_row_id):
    """Return ownerKey → displayName from salesforce_connection_owners."""
    connection_row_id = _row_id(connection_row_id)
    if not connection_row_id.isdigit():
        return {}
    try:
        # select * matches directory sync. Selecting the boolean column
        # `active` by name is rejected by some Catalyst ZCQL parsers.
        results = zcql.execute_query(
            f"select * from {SALESFORCE_DIRECTORY_TABLE} where "
            f"connection_row_id = {connection_row_id}"
        )
    except Exception as exc:  # noqa: BLE001 - names are optional presentation metadata
        LOGGER.warning("Could not read Salesforce owner directory: %s", exc)
        return {}
    names = {}
    for row in _zcql_rows(results, SALESFORCE_DIRECTORY_TABLE):
        active_value = _column(row, "active")
        if active_value is not None and not _is_true(active_value):
            continue
        crm_user_id = _normalize_salesforce_id(_column(row, "crm_user_id"))
        if not crm_user_id:
            continue
        display_name = str(_column(row, "display_name") or "Unknown owner")
        for key in directory_lookup_keys(crm_user_id):
            names[key] = display_name
    return names


def ensure_salesforce_owner_directory(
    datastore, zcql, connection_row, *, refresh=False
):
    """Load the cached directory; sync Users+Groups once when empty or refresh=True."""
    connection_row_id = _row_id((connection_row or {}).get("ROWID"))
    directory = load_salesforce_owner_directory(zcql, connection_row_id)
    if directory and not refresh:
        return directory
    if not connection_row or not connection_row_id.isdigit():
        return directory
    try:
        from salesforce.client import get_salesforce_access_token

        access_token, instance_url = get_salesforce_access_token(
            datastore, connection_row
        )
        result = sync_salesforce_owner_directory(
            datastore, zcql, connection_row, access_token, instance_url
        )
    except Exception as exc:  # noqa: BLE001 - unresolved owners stay Unknown owner
        LOGGER.warning("Salesforce owner directory sync skipped: %s", exc)
        return load_salesforce_owner_directory(zcql, connection_row_id)
    directory = load_salesforce_owner_directory(zcql, connection_row_id)
    if not directory:
        warning = (result or {}).get("warning") or "no owner rows were stored"
        LOGGER.warning(
            "Salesforce owner directory sync did not persist owners "
            "connection_row_id=%s: %s",
            connection_row_id,
            warning,
        )
    elif result and not result.get("refreshed") and result.get("warning"):
        LOGGER.warning(
            "Salesforce owner directory sync reported a warning "
            "connection_row_id=%s: %s",
            connection_row_id,
            result["warning"],
        )
    return directory


def resolve_owner_identity(raw_value, owner_directory):
    """Resolve a Zoho Owner object/id or a Salesforce OwnerId to a stable owner key."""
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
            owner_name = str(
                decoded.get("name") or decoded.get("full_name") or ""
            ).strip()
        else:
            salesforce_id = _normalize_salesforce_id(value)
            if salesforce_id.isdigit() or is_salesforce_record_id(salesforce_id):
                owner_id = salesforce_id
            else:
                owner_name = value
    if not owner_id and not owner_name:
        owner_name = "Unassigned"
        owner_key = _canonical_hash({"owner_state": "unassigned"})
    elif owner_id:
        owner_key = crm_user_owner_key(owner_id)
        owner_name = lookup_owner_display_name(
            owner_id, owner_directory, owner_name or "Unknown owner"
        )
    else:
        owner_key = _canonical_hash({"owner_name": owner_name.casefold()})
    return {
        "ownerKey": owner_key,
        "ownerId": owner_id,
        "ownerName": owner_name,
    }
