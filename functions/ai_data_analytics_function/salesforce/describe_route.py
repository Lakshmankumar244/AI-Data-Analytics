"""HTTP-only Salesforce object describe with tenant-aware connection access.

Provider field describe stays in salesforce.describe so the shared/worker
copy is not coupled to Marketplace installation authorization.
"""

import logging

import zcatalyst_sdk
from flask import Request

from common.core import DiscoveryError, get_current_user_id, json_response
from installations.authorization import find_accessible_connected_connection
from installations.repository import SALESFORCE_CONNECTIONS_TABLE
from salesforce.client import get_salesforce_access_token
from salesforce.describe import (
    describe_salesforce_fields,
    fetch_sobject_describe,
    is_safe_sobject_api_name,
)

logger = logging.getLogger(__name__)


def get_salesforce_object_describe(request: Request, datastore, object_api_name: str):
    if not is_safe_sobject_api_name(object_api_name):
        return json_response(
            {
                "error": {
                    "code": "INVALID_OBJECT_API_NAME",
                    "message": "Salesforce object name is invalid",
                }
            },
            400,
        )

    user_id = get_current_user_id(request)
    zcql = zcatalyst_sdk.initialize().zcql()
    row = find_accessible_connected_connection(
        zcql, SALESFORCE_CONNECTIONS_TABLE, user_id
    )
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
        payload = fetch_sobject_describe(access_token, instance_url, object_api_name)
        described = describe_salesforce_fields(payload)
    except DiscoveryError as exc:
        logger.exception(
            "Salesforce field describe failed for user %s object %s with %s",
            user_id,
            object_api_name,
            exc.code,
        )
        status = 404 if exc.code == "OBJECT_NOT_FOUND" else 502
        return json_response(
            {"error": {"code": exc.code, "message": str(exc)}},
            status,
        )
    except Exception:  # noqa: BLE001 - keep provider details server-side
        logger.exception(
            "Unexpected Salesforce field describe failure for user %s object %s",
            user_id,
            object_api_name,
        )
        return json_response(
            {
                "error": {
                    "code": "SALESFORCE_DESCRIBE_FAILED",
                    "message": "Salesforce field metadata could not be read",
                }
            },
            500,
        )

    return json_response(
        {
            "connectionId": str(row["ROWID"]),
            "object": described["object"],
            "allowlist": described["allowlist"],
            "fields": described["fields"],
        }
    )
