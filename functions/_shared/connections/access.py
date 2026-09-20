"""Resolve the Zoho connection for a scan action."""

from common.core import get_current_user_id
from connections.repository import (
    find_persisted_scan_connection,
    find_scan_connection,
)


def resolve_action_connection(zcql, scan_row, request=None, connection_row=None):
    """Prefer an explicit row, then request ownership, then persisted scan state."""
    if connection_row is not None:
        if str(connection_row.get("status") or "") != "connected":
            return None
        return connection_row
    if request is not None:
        user_id = get_current_user_id(request)
        return find_scan_connection(zcql, user_id, scan_row)
    return find_persisted_scan_connection(zcql, scan_row)
