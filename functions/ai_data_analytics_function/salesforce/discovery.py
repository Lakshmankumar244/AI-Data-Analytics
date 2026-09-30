"""Authenticated Salesforce organization and object discovery route."""

import logging

import zcatalyst_sdk
from flask import Request

from common.core import DiscoveryError, get_current_user_id, json_response
from installations.authorization import find_accessible_connected_connection
from installations.repository import SALESFORCE_CONNECTIONS_TABLE
from salesforce.client import (
    fetch_accessible_sobjects,
    fetch_salesforce_organization,
    get_salesforce_access_token,
    persist_salesforce_organization_name,
)

logger = logging.getLogger(__name__)


def _select_salesforce_connection(zcql, user_id: str):
    """Prefer the exclusive-active Salesforce row the caller can access."""
    return find_accessible_connected_connection(
        zcql, SALESFORCE_CONNECTIONS_TABLE, user_id
    )


def get_salesforce_metadata(request: Request, datastore):
    user_id = get_current_user_id(request)
    zcql = zcatalyst_sdk.initialize().zcql()
    row = _select_salesforce_connection(zcql, user_id)
    if not row:
        return json_response(
            {
                "error": {
                    "code": "SALESFORCE_CONNECTION_REQUIRED",
                    "message": "Connect Salesforce CRM",
                }
            },
            409,
        )

    try:
        access_token, instance_url = get_salesforce_access_token(datastore, row)
        organization = fetch_salesforce_organization(
            access_token, instance_url, row
        )
        persist_salesforce_organization_name(datastore, row, organization)
        objects = fetch_accessible_sobjects(access_token, instance_url)
    except DiscoveryError as exc:
        logger.exception(
            "Salesforce metadata discovery failed for user %s with %s",
            user_id,
            exc.code,
        )
        return json_response(
            {"error": {"code": exc.code, "message": str(exc)}},
            502,
        )
    except Exception:  # noqa: BLE001 - keep provider details server-side
        logger.exception(
            "Unexpected Salesforce metadata discovery failure for user %s",
            user_id,
        )
        return json_response(
            {
                "error": {
                    "code": "SALESFORCE_DISCOVERY_FAILED",
                    "message": "Salesforce metadata could not be read",
                }
            },
            500,
        )

    return json_response(
        {
            "connectionId": str(row["ROWID"]),
            "organization": {
                "id": organization["id"],
                "name": organization["name"],
                "timeZone": organization.get("timeZone") or "",
                "isSandbox": organization.get("isSandbox"),
                "organizationType": organization.get("organizationType") or "",
            },
            "objects": objects,
        }
    )
