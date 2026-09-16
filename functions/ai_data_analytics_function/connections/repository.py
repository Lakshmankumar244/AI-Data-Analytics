"""Connection lookups shared by scan and provider routes."""

from common.core import foreign_row_id


def _escape(value):
    return str(value).replace("'", "''")


def _rows(zcql, query):
    return [item["zoho_connections"] for item in zcql.execute_query(query)]


def _is_true(value):
    return value is True or str(value).strip().lower() == "true"


def connection_is_active(row):
    return _is_true((row or {}).get("is_active"))


def scan_crm_provider(scan_row):
    """Return the CRM that owns scan_jobs.connection_row_id. Missing means Zoho."""
    value = str((scan_row or {}).get("crm_provider") or "zoho").strip().lower()
    return value or "zoho"


def find_active_connection(zcql, user_id):
    """Return the user's selected, healthy Zoho connection."""
    rows = _rows(
        zcql,
        "select * from zoho_connections where "
        f"user_id = '{_escape(user_id)}' and status = 'connected'",
    )
    active = [row for row in rows if connection_is_active(row)]
    if not active:
        return None
    active.sort(
        key=lambda row: (str(row.get("last_selected_at") or ""), str(row.get("ROWID") or "")),
        reverse=True,
    )
    return active[0]


def find_connected_connection(zcql, user_id):
    """Return a connected Zoho row for listing. is_active is preference, not a filter."""
    rows = _rows(
        zcql,
        "select * from zoho_connections where "
        f"user_id = '{_escape(user_id)}' and status = 'connected'",
    )
    if not rows:
        return None
    rows.sort(
        key=lambda row: (
            connection_is_active(row),
            str(row.get("last_selected_at") or ""),
            str(row.get("ROWID") or ""),
        ),
        reverse=True,
    )
    return rows[0]


def find_persisted_scan_connection(zcql, scan_row):
    """Load the scan's stored Zoho connection without a request user session."""
    if scan_crm_provider(scan_row) == "salesforce":
        return None
    connection_row_id = str(foreign_row_id(scan_row.get("connection_row_id")) or "")
    if not connection_row_id.isdigit():
        return None
    rows = _rows(
        zcql,
        "select * from zoho_connections where "
        f"ROWID = {connection_row_id} "
        "and status = 'connected' limit 1",
    )
    return rows[0] if rows else None


def find_scan_connection(zcql, user_id, scan_row):
    """Resolve a scan's original Zoho connection and verify authenticated ownership."""
    if scan_crm_provider(scan_row) == "salesforce":
        return None
    connection_row_id = str(foreign_row_id(scan_row.get("connection_row_id")) or "")
    if not connection_row_id.isdigit():
        return None
    rows = _rows(
        zcql,
        "select * from zoho_connections where "
        f"ROWID = {connection_row_id} "
        f"and user_id = '{_escape(user_id)}' "
        "and status = 'connected' limit 1",
    )
    return rows[0] if rows else None
