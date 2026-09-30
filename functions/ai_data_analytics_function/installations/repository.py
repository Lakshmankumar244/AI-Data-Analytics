"""Data Store access for Marketplace installations and connection linkage.

These helpers read and write the Console-created tables and the nullable
`installation_id` column on CRM connections. They do not create installations
during OAuth, assign membership, or change authorization. Callers that omit
`installation_id` leave the column unset (null).
"""

from common.core import foreign_row_id
from connections.activation import CONNECTION_TABLES
from installations.models import installation_from_row, member_from_row

INSTALLATIONS_TABLE = "marketplace_installations"
MEMBERS_TABLE = "installation_members"
ZOHO_CONNECTIONS_TABLE = "zoho_connections"
SALESFORCE_CONNECTIONS_TABLE = "salesforce_connections"
INSTALLATION_ID_COLUMN = "installation_id"

SOURCE_MARKETPLACE = "marketplace"
SOURCE_STANDALONE = "standalone"
STATUS_ACTIVE = "active"

_INSTALLATION_OPTIONAL_COLUMNS = (
    "zoho_org_id",
    "salesforce_org_id",
    "organization_name",
)


def _escape(value):
    return str(value).replace("'", "''")


def _text(value):
    return str(value or "").strip()


def _rows(zcql, query, table_name):
    return [item[table_name] for item in zcql.execute_query(query)]


def _one(zcql, query, table_name):
    rows = _rows(zcql, query, table_name)
    return rows[0] if rows else None


def normalize_installation_id(value):
    """Return a numeric installation ROWID, or None when the value is empty.

    Catalyst connection `installation_id` is nullable. Blank values must not be
    written, so existing rows keep a null column and stay on user_id ownership.
    """
    row_id = str(foreign_row_id(value) or "").strip()
    return row_id if row_id.isdigit() else None


def connection_installation_id(row):
    """Read nullable installation_id from a Zoho or Salesforce connection row."""
    return normalize_installation_id((row or {}).get(INSTALLATION_ID_COLUMN))


def with_optional_installation_id(fields):
    """Copy persist fields, including installation_id only when it is a ROWID.

    Absent, blank, or non-numeric values are omitted so insert/update does not
    overwrite a null column or write an empty string.
    """
    row = dict(fields or {})
    if INSTALLATION_ID_COLUMN not in row:
        return row
    installation_id = normalize_installation_id(row.get(INSTALLATION_ID_COLUMN))
    if installation_id is None:
        row.pop(INSTALLATION_ID_COLUMN, None)
    else:
        row[INSTALLATION_ID_COLUMN] = installation_id
    return row


def connection_row_for_persist(user_id, fields):
    """Build a Zoho/Salesforce connection persist payload for the given user."""
    return with_optional_installation_id({"user_id": user_id, **dict(fields or {})})


def set_connection_installation_id(
    datastore, table_name, connection_row_id, installation_id
):
    """Write installation_id on one CRM connection row. Does not create tenants."""
    if table_name not in CONNECTION_TABLES:
        raise ValueError("Unsupported connection table")
    row_id = str(foreign_row_id(connection_row_id) or "").strip()
    if not row_id.isdigit():
        raise ValueError("Connection identifier is invalid")
    normalized = normalize_installation_id(installation_id)
    if normalized is None:
        raise ValueError("installation_id is invalid")
    return datastore.table(table_name).update_row(
        {"ROWID": row_id, INSTALLATION_ID_COLUMN: normalized}
    )


def find_installation_by_row_id(zcql, row_id):
    normalized = normalize_installation_id(row_id)
    if not normalized:
        return None
    return _one(
        zcql,
        f"select * from {INSTALLATIONS_TABLE} where "
        f"ROWID = {normalized} limit 1",
        INSTALLATIONS_TABLE,
    )


def find_installation_by_key(zcql, installation_key):
    key = _text(installation_key)
    if not key:
        return None
    return _one(
        zcql,
        f"select * from {INSTALLATIONS_TABLE} where "
        f"installation_key = '{_escape(key)}' limit 1",
        INSTALLATIONS_TABLE,
    )


def find_installation_by_zoho_org_id(zcql, zoho_org_id, source=None):
    org_id = _text(zoho_org_id)
    if not org_id:
        return None
    source_clause = ""
    wanted_source = _text(source)
    if wanted_source:
        source_clause = f" and source = '{_escape(wanted_source)}'"
    return _one(
        zcql,
        f"select * from {INSTALLATIONS_TABLE} where "
        f"zoho_org_id = '{_escape(org_id)}'{source_clause} limit 1",
        INSTALLATIONS_TABLE,
    )


def find_installation_by_salesforce_org_id(zcql, salesforce_org_id):
    org_id = _text(salesforce_org_id)
    if not org_id:
        return None
    return _one(
        zcql,
        f"select * from {INSTALLATIONS_TABLE} where "
        f"salesforce_org_id = '{_escape(org_id)}' limit 1",
        INSTALLATIONS_TABLE,
    )


def installation_persist_fields(fields):
    """Return insert/update columns for marketplace_installations.

    Does not generate keys or default a source. Callers must supply
    `installation_key` and `source`. Empty optional org fields are omitted
    so they stay null.
    """
    data = dict(fields or {})
    installation_key = _text(data.get("installation_key"))
    source = _text(data.get("source"))
    if not installation_key:
        raise ValueError("installation_key is required")
    if not source:
        raise ValueError("source is required")
    row = {
        "installation_key": installation_key,
        "source": source,
        "status": _text(data.get("status")) or STATUS_ACTIVE,
    }
    for column in _INSTALLATION_OPTIONAL_COLUMNS:
        value = _text(data.get(column))
        if value:
            row[column] = value
    return row


def insert_installation_row(datastore, fields):
    """Insert one marketplace_installations row from caller-supplied fields."""
    return datastore.table(INSTALLATIONS_TABLE).insert_row(
        installation_persist_fields(fields)
    )


def update_installation_row(datastore, row_id, fields):
    """Update one marketplace_installations row. Does not assign connections."""
    normalized = normalize_installation_id(row_id)
    if not normalized:
        raise ValueError("installation identifier is invalid")
    updates = dict(fields or {})
    persist = {"ROWID": normalized}
    if "installation_key" in updates:
        key = _text(updates.get("installation_key"))
        if not key:
            raise ValueError("installation_key is required")
        persist["installation_key"] = key
    if "source" in updates:
        source = _text(updates.get("source"))
        if not source:
            raise ValueError("source is required")
        persist["source"] = source
    if "status" in updates:
        persist["status"] = _text(updates.get("status")) or STATUS_ACTIVE
    for column in _INSTALLATION_OPTIONAL_COLUMNS:
        if column not in updates:
            continue
        value = _text(updates.get(column))
        if value:
            persist[column] = value
    return datastore.table(INSTALLATIONS_TABLE).update_row(persist)


def member_persist_fields(fields):
    """Return insert/update columns for installation_members."""
    data = dict(fields or {})
    installation_id = normalize_installation_id(data.get("installation_id"))
    catalyst_user_id = _text(data.get("catalyst_user_id"))
    if not installation_id:
        raise ValueError("installation_id is required")
    if not catalyst_user_id:
        raise ValueError("catalyst_user_id is required")
    row = {
        "installation_id": installation_id,
        "catalyst_user_id": catalyst_user_id,
        "status": _text(data.get("status")) or STATUS_ACTIVE,
    }
    zoho_user_id = _text(data.get("zoho_user_id"))
    if zoho_user_id:
        row["zoho_user_id"] = zoho_user_id
    return row


def insert_member_row(datastore, fields):
    """Insert one installation_members row from caller-supplied fields."""
    return datastore.table(MEMBERS_TABLE).insert_row(member_persist_fields(fields))


def update_member_row(datastore, row_id, fields):
    """Update one installation_members row. Does not change authorization."""
    normalized = normalize_installation_id(row_id)
    if not normalized:
        raise ValueError("member identifier is invalid")
    persist = member_persist_fields(fields)
    persist["ROWID"] = normalized
    return datastore.table(MEMBERS_TABLE).update_row(persist)


def find_member(zcql, installation_id, catalyst_user_id):
    normalized = normalize_installation_id(installation_id)
    user_id = _text(catalyst_user_id)
    if not normalized or not user_id:
        return None
    return _one(
        zcql,
        f"select * from {MEMBERS_TABLE} where "
        f"installation_id = '{_escape(normalized)}' and "
        f"catalyst_user_id = '{_escape(user_id)}' limit 1",
        MEMBERS_TABLE,
    )


def find_members_for_installation(zcql, installation_id):
    normalized = normalize_installation_id(installation_id)
    if not normalized:
        return []
    return _rows(
        zcql,
        f"select * from {MEMBERS_TABLE} where "
        f"installation_id = '{_escape(normalized)}'",
        MEMBERS_TABLE,
    )


def find_memberships_for_user(zcql, catalyst_user_id):
    user_id = _text(catalyst_user_id)
    if not user_id:
        return []
    return _rows(
        zcql,
        f"select * from {MEMBERS_TABLE} where "
        f"catalyst_user_id = '{_escape(user_id)}'",
        MEMBERS_TABLE,
    )


def find_zoho_connections_by_installation(zcql, installation_id):
    normalized = normalize_installation_id(installation_id)
    if not normalized:
        return []
    return _rows(
        zcql,
        f"select * from {ZOHO_CONNECTIONS_TABLE} where "
        f"{INSTALLATION_ID_COLUMN} = '{_escape(normalized)}'",
        ZOHO_CONNECTIONS_TABLE,
    )


def find_salesforce_connections_by_installation(zcql, installation_id):
    normalized = normalize_installation_id(installation_id)
    if not normalized:
        return []
    return _rows(
        zcql,
        f"select * from {SALESFORCE_CONNECTIONS_TABLE} where "
        f"{INSTALLATION_ID_COLUMN} = '{_escape(normalized)}'",
        SALESFORCE_CONNECTIONS_TABLE,
    )


def as_installation(row):
    return installation_from_row(row) if row else None


def as_member(row):
    return member_from_row(row) if row else None
