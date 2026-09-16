"""Exclusive is_active selection across Zoho and Salesforce connection tables."""

import logging
from datetime import datetime, timezone

from common.core import to_catalyst_column_datetime

logger = logging.getLogger(__name__)

ZOHO_CONNECTIONS_TABLE = "zoho_connections"
SALESFORCE_CONNECTIONS_TABLE = "salesforce_connections"
CONNECTION_TABLES = (ZOHO_CONNECTIONS_TABLE, SALESFORCE_CONNECTIONS_TABLE)


def _escape(value):
    return str(value).replace("'", "''")


def _is_true(value):
    return value is True or str(value).strip().lower() == "true"


def _active_rows(zcql, table_name, user_id):
    if table_name not in CONNECTION_TABLES:
        raise ValueError("Unsupported connection table")
    results = zcql.execute_query(
        f"select ROWID,is_active from {table_name} where "
        f"user_id = '{_escape(user_id)}'"
    )
    return [
        item[table_name]
        for item in results
        if _is_true(item[table_name].get("is_active"))
    ]


def activate_exclusive_connection(datastore, zcql, user_id, table_name, selected_row_id):
    """Activate one owned row and clear is_active on every other CRM connection.

    On failure, previously active rows are restored so the user is not left
    with two actives or an unintended empty selection.
    """
    if table_name not in CONNECTION_TABLES:
        raise ValueError("Unsupported connection table")

    selected_id = str(selected_row_id)
    previous = []
    for name in CONNECTION_TABLES:
        for row in _active_rows(zcql, name, user_id):
            previous.append((name, str(row["ROWID"])))
    previously_active = set(previous)
    to_deactivate = [
        item for item in previous if item != (table_name, selected_id)
    ]

    try:
        for name, row_id in to_deactivate:
            datastore.table(name).update_row({"ROWID": row_id, "is_active": False})
        datastore.table(table_name).update_row(
            {
                "ROWID": selected_id,
                "is_active": True,
                "last_selected_at": to_catalyst_column_datetime(
                    datetime.now(timezone.utc)
                ),
            }
        )
    except Exception:
        logger.exception(
            "Exclusive connection activation failed for user %s; restoring previous active rows",
            user_id,
        )
        for name, row_id in previous:
            try:
                datastore.table(name).update_row({"ROWID": row_id, "is_active": True})
            except Exception:
                logger.exception(
                    "Could not restore previous active connection in %s", name
                )
        if (table_name, selected_id) not in previously_active:
            try:
                datastore.table(table_name).update_row(
                    {"ROWID": selected_id, "is_active": False}
                )
            except Exception:
                logger.exception(
                    "Could not clear failed activation target in %s", table_name
                )
        raise
