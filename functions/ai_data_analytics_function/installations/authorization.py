"""Tenant-aware installation membership and connection access helpers.

HTTP connection and existing-scan access use dual-read authorization.
Scan creation uses accessible active connections. Workers still authorize
by persisted connection rows without a request user.
"""

from common.core import foreign_row_id
from installations.repository import (
    SALESFORCE_CONNECTIONS_TABLE,
    STATUS_ACTIVE,
    ZOHO_CONNECTIONS_TABLE,
    connection_installation_id,
    find_installation_by_row_id,
    find_member,
    find_memberships_for_user,
    find_salesforce_connections_by_installation,
    find_zoho_connections_by_installation,
    normalize_installation_id,
)


def _text(value):
    return str(value or "").strip()


def _status_is_active(value):
    return _text(value).lower() == STATUS_ACTIVE


def installation_is_active(row):
    """True when a marketplace_installations row is usable as a tenant."""
    return bool(row) and _status_is_active((row or {}).get("status"))


def member_is_active(row):
    """True when an installation_members row is an active membership."""
    return bool(row) and _status_is_active((row or {}).get("status"))


def connection_owned_by_user(connection_row, user_id):
    """Standalone ownership: the connection's Catalyst user_id matches the caller."""
    return _text((connection_row or {}).get("user_id")) == _text(user_id) and bool(
        _text(user_id)
    )


def resolve_active_installation_for_user(zcql, installation_id, catalyst_user_id):
    """Return the installation row when it is active and the user is an active member.

    Non-members, missing installations, and disabled installations return None.
    """
    installation = find_installation_by_row_id(zcql, installation_id)
    if not installation_is_active(installation):
        return None
    member = find_member(zcql, installation_id, catalyst_user_id)
    if not member_is_active(member):
        return None
    return installation


def resolve_connection_through_installation(zcql, connection_row, catalyst_user_id):
    """Return the connection when its installation_id is an active tenant the user belongs to.

    Does not fall back to user_id. Connections without installation_id return None.
    A member of another installation cannot use this path.
    """
    installation_id = connection_installation_id(connection_row)
    if not installation_id:
        return None
    installation = resolve_active_installation_for_user(
        zcql, installation_id, catalyst_user_id
    )
    if not installation:
        return None
    if normalize_installation_id(installation) != installation_id:
        return None
    return connection_row


def resolve_connection_access(zcql, connection_row, user_id):
    """Dual-read access for connection HTTP APIs.

    Marketplace-linked connections resolve through active installation membership.
    Standalone connections (null installation_id) resolve through user_id.
    """
    if not connection_row:
        return None
    if connection_installation_id(connection_row):
        return resolve_connection_through_installation(
            zcql, connection_row, user_id
        )
    if connection_owned_by_user(connection_row, user_id):
        return connection_row
    return None


def _load_connection(zcql, table_name, connection_row_id):
    row_id = str(foreign_row_id(connection_row_id) or "").strip()
    if table_name not in {ZOHO_CONNECTIONS_TABLE, SALESFORCE_CONNECTIONS_TABLE}:
        raise ValueError("Unsupported connection table")
    if not row_id.isdigit():
        return None
    results = zcql.execute_query(
        f"select * from {table_name} where ROWID = {row_id} limit 1"
    )
    if not results:
        return None
    return results[0][table_name]


def find_accessible_zoho_connection(zcql, connection_row_id, user_id):
    """Load a Zoho connection and apply dual-read access."""
    row = _load_connection(zcql, ZOHO_CONNECTIONS_TABLE, connection_row_id)
    return resolve_connection_access(zcql, row, user_id)


def find_accessible_salesforce_connection(zcql, connection_row_id, user_id):
    """Load a Salesforce connection and apply dual-read access."""
    row = _load_connection(zcql, SALESFORCE_CONNECTIONS_TABLE, connection_row_id)
    return resolve_connection_access(zcql, row, user_id)


def _escape(value):
    return str(value).replace("'", "''")


def _is_connected(row):
    return str((row or {}).get("status") or "") == "connected"


def _is_selected(row):
    value = (row or {}).get("is_active")
    return value is True or str(value).strip().lower() == "true"


def _connection_preference_key(row):
    return (
        _is_selected(row),
        str((row or {}).get("last_selected_at") or ""),
        str((row or {}).get("ROWID") or ""),
    )


def _rows_owned_by_user(zcql, table_name, user_id):
    results = zcql.execute_query(
        f"select * from {table_name} where user_id = '{_escape(user_id)}'"
    )
    return [item[table_name] for item in results]


def _rows_for_memberships(zcql, table_name, user_id):
    finder = (
        find_zoho_connections_by_installation
        if table_name == ZOHO_CONNECTIONS_TABLE
        else find_salesforce_connections_by_installation
    )
    rows = []
    for membership in find_memberships_for_user(zcql, user_id):
        if not member_is_active(membership):
            continue
        installation_id = normalize_installation_id(membership.get("installation_id"))
        if not installation_id:
            continue
        if not resolve_active_installation_for_user(zcql, installation_id, user_id):
            continue
        rows.extend(finder(zcql, installation_id))
    return rows


def list_accessible_connections(zcql, table_name, user_id, *, connected_only=False):
    """CRM rows the caller may use: standalone owner or active member."""
    if table_name not in {ZOHO_CONNECTIONS_TABLE, SALESFORCE_CONNECTIONS_TABLE}:
        raise ValueError("Unsupported connection table")
    seen = {}
    for row in _rows_owned_by_user(zcql, table_name, user_id):
        seen[str(row.get("ROWID") or "")] = row
    for row in _rows_for_memberships(zcql, table_name, user_id):
        seen[str(row.get("ROWID") or "")] = row
    accessible = []
    for row_id, row in seen.items():
        if not row_id:
            continue
        if connected_only and not _is_connected(row):
            continue
        if resolve_connection_access(zcql, row, user_id):
            accessible.append(row)
    accessible.sort(key=_connection_preference_key, reverse=True)
    return accessible


def list_accessible_connected_connections(zcql, table_name, user_id):
    """Connected CRM rows the caller may list: standalone owner or active member."""
    return list_accessible_connections(
        zcql, table_name, user_id, connected_only=True
    )


def find_accessible_connected_connection(zcql, table_name, user_id):
    """Preferred connected row among dual-read accessible connections."""
    rows = list_accessible_connected_connections(zcql, table_name, user_id)
    return rows[0] if rows else None


def find_accessible_active_connection(zcql, table_name, user_id):
    """Exclusive-active row among dual-read accessible connections."""
    active = [
        row
        for row in list_accessible_connected_connections(zcql, table_name, user_id)
        if _is_selected(row)
    ]
    return active[0] if active else None


def find_accessible_connected_connection_by_id(zcql, table_name, connection_row_id, user_id):
    """Load one connected row and apply dual-read access."""
    row = _load_connection(zcql, table_name, connection_row_id)
    if not _is_connected(row):
        return None
    return resolve_connection_access(zcql, row, user_id)
