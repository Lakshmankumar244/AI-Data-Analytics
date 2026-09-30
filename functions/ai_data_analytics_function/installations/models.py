"""Named representations of Marketplace installation Data Store rows.

These are in-process helpers only. They are not API serializers and are not
used for authorization in Migration 3A.
"""

from collections import namedtuple


Installation = namedtuple(
    "Installation",
    (
        "row_id",
        "installation_key",
        "source",
        "zoho_org_id",
        "salesforce_org_id",
        "organization_name",
        "status",
    ),
)

InstallationMember = namedtuple(
    "InstallationMember",
    (
        "row_id",
        "installation_id",
        "catalyst_user_id",
        "zoho_user_id",
        "status",
    ),
)


def _text(value):
    return str(value or "").strip()


def installation_from_row(row):
    """Map a marketplace_installations Data Store dict to Installation."""
    data = row or {}
    return Installation(
        row_id=_text(data.get("ROWID") or data.get("rowid")),
        installation_key=_text(data.get("installation_key")),
        source=_text(data.get("source")),
        zoho_org_id=_text(data.get("zoho_org_id")),
        salesforce_org_id=_text(data.get("salesforce_org_id")),
        organization_name=_text(data.get("organization_name")),
        status=_text(data.get("status")),
    )


def member_from_row(row):
    """Map an installation_members Data Store dict to InstallationMember."""
    data = row or {}
    return InstallationMember(
        row_id=_text(data.get("ROWID") or data.get("rowid")),
        installation_id=_text(data.get("installation_id")),
        catalyst_user_id=_text(data.get("catalyst_user_id")),
        zoho_user_id=_text(data.get("zoho_user_id")),
        status=_text(data.get("status")),
    )
