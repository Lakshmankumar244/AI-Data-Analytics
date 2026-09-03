"""Connection lookups shared by scan and provider routes."""

from common.core import foreign_row_id


def _escape(value):
    return str(value).replace("'", "''")


def _rows(zcql, query):
    return [item["zoho_connections"] for item in zcql.execute_query(query)]


def _is_true(value):
    return value is True or str(value).strip().lower() == "true"


def find_active_connection(zcql, user_id):
    """Return the user's selected, healthy Zoho connection."""
    rows = _rows(
        zcql,
        "select * from zoho_connections where "
        f"user_id = '{_escape(user_id)}' and status = 'connected'",
    )
    active = [row for row in rows if _is_true(row.get("is_active"))]
    if not active:
        return None
    active.sort(
        key=lambda row: (str(row.get("last_selected_at") or ""), str(row.get("ROWID") or "")),
        reverse=True,
    )
    return active[0]


def find_scan_connection(zcql, user_id, scan_row):
    """Resolve a scan's original connection and verify authenticated ownership."""
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
