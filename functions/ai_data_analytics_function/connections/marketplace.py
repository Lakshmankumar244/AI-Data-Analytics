"""Link a Marketplace Zoho OAuth grant to an installation without backfill.

Standalone OAuth must not import or call this module. Existing connection rows
with a null installation_id are never updated here.
"""

from installations.repository import connection_installation_id, connection_row_for_persist
from installations.service import resolve_or_create_marketplace_installation


def _escape(value):
    return str(value).replace("'", "''")


def _is_true(value):
    return value is True or str(value).strip().lower() == "true"


def _connection_identity_matches(row, fields):
    if str(row.get("zoho_org_id") or "") != str(fields.get("zoho_org_id") or ""):
        return False
    if str(row.get("zoho_user_id") or "") == str(fields.get("zoho_user_id") or ""):
        return True
    return not row.get("zoho_user_id") and (
        str(row.get("connected_email") or "").strip().lower()
        == str(fields.get("connected_email") or "").strip().lower()
    )


def _deactivate_other_connections(table, existing_rows, selected_row_id):
    for connection in existing_rows:
        if str(connection["ROWID"]) != selected_row_id and _is_true(
            connection.get("is_active")
        ):
            table.update_row({"ROWID": connection["ROWID"], "is_active": False})


def persist_marketplace_zoho_oauth_connection(
    datastore, zcql, user_id, organization, profile, fields
):
    """Resolve the Marketplace installation, then upsert a linked Zoho connection.

    `fields` is the existing zoho_connections payload (including tokens).
    Tokens are written only to zoho_connections. Installation/member rows never
    receive OAuth credentials. Standalone rows for the same user/org are not
    backfilled.
    """
    resolved = resolve_or_create_marketplace_installation(
        datastore,
        zcql,
        zoho_org_id=organization["id"],
        catalyst_user_id=user_id,
        organization_name=organization.get("company_name", ""),
        zoho_user_id=profile.get("user_id", ""),
    )
    installation_id = resolved["installation_id"]
    persist_fields = {**dict(fields or {}), "installation_id": installation_id}

    table = datastore.table("zoho_connections")
    existing = zcql.execute_query(
        "select * from zoho_connections where "
        f"user_id = '{_escape(user_id)}'"
    )
    existing_rows = [item["zoho_connections"] for item in existing]
    target = next(
        (
            row
            for row in existing_rows
            if connection_installation_id(row) == installation_id
            and _connection_identity_matches(row, persist_fields)
        ),
        None,
    )
    row_data = connection_row_for_persist(user_id, persist_fields)
    if target:
        row_data["ROWID"] = target["ROWID"]
        selected = table.update_row(row_data)
    else:
        selected = table.insert_row(row_data)

    _deactivate_other_connections(table, existing_rows, str(selected["ROWID"]))
    return {
        **resolved,
        "connection": selected,
    }
