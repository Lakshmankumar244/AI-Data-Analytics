"""Resolve or create a Zoho Marketplace installation and membership.

This layer is not invoked by standalone OAuth. It does not change
user_id authorization, backfill connections, or reuse standalone
installations for a different Catalyst user.
"""

from installations.repository import (
    SOURCE_MARKETPLACE,
    STATUS_ACTIVE,
    find_installation_by_zoho_org_id,
    find_member,
    insert_installation_row,
    insert_member_row,
    normalize_installation_id,
    update_installation_row,
    update_member_row,
)


def _text(value):
    return str(value or "").strip()


def marketplace_zoho_installation_key(zoho_org_id):
    """Stable key for a Marketplace install of one Zoho CRM organization."""
    org_id = _text(zoho_org_id)
    if not org_id:
        raise ValueError("zoho_org_id is required")
    return f"marketplace:zoho:{org_id}"


def resolve_or_create_marketplace_installation(
    datastore,
    zcql,
    zoho_org_id,
    catalyst_user_id,
    organization_name="",
    zoho_user_id="",
):
    """Return the Marketplace installation and member for a Zoho organization.

    Reuses an existing `source=marketplace` row for the same `zoho_org_id`.
    Standalone installations with the same org id are ignored. Membership is
    reused for the same Catalyst user on that Marketplace row.
    """
    org_id = _text(zoho_org_id)
    user_id = _text(catalyst_user_id)
    if not org_id:
        raise ValueError("zoho_org_id is required")
    if not user_id:
        raise ValueError("catalyst_user_id is required")

    name = _text(organization_name)
    connected_zoho_user_id = _text(zoho_user_id)

    installation = find_installation_by_zoho_org_id(
        zcql, org_id, source=SOURCE_MARKETPLACE
    )
    created_installation = False
    if installation is None:
        installation = insert_installation_row(
            datastore,
            {
                "installation_key": marketplace_zoho_installation_key(org_id),
                "source": SOURCE_MARKETPLACE,
                "zoho_org_id": org_id,
                "organization_name": name,
                "status": STATUS_ACTIVE,
            },
        )
        created_installation = True
    elif name and name != _text(installation.get("organization_name")):
        update_installation_row(
            datastore,
            installation["ROWID"],
            {"organization_name": name},
        )
        installation = {**installation, "organization_name": name}

    installation_id = normalize_installation_id(installation)
    if not installation_id:
        raise ValueError("installation identifier is invalid")

    member = find_member(zcql, installation_id, user_id)
    created_member = False
    if member is None:
        member = insert_member_row(
            datastore,
            {
                "installation_id": installation_id,
                "catalyst_user_id": user_id,
                "zoho_user_id": connected_zoho_user_id,
                "status": STATUS_ACTIVE,
            },
        )
        created_member = True
    elif connected_zoho_user_id and not _text(member.get("zoho_user_id")):
        update_member_row(
            datastore,
            member["ROWID"],
            {
                "installation_id": installation_id,
                "catalyst_user_id": user_id,
                "zoho_user_id": connected_zoho_user_id,
                "status": _text(member.get("status")) or STATUS_ACTIVE,
            },
        )
        member = {**member, "zoho_user_id": connected_zoho_user_id}

    return {
        "installation_id": installation_id,
        "installation": installation,
        "member": member,
        "created_installation": created_installation,
        "created_member": created_member,
    }
