"""Refresh a persisted Zoho connection token without request-scoped auth."""

import logging
import os
from datetime import datetime, timedelta, timezone

import requests

from common.core import (
    DiscoveryError,
    from_catalyst_datetime,
    to_catalyst_datetime,
)

logger = logging.getLogger(__name__)


def get_connection_access_token(datastore, connection_row: dict):
    expires_at_value = connection_row.get("token_expires_at")
    if expires_at_value:
        try:
            expires_at = from_catalyst_datetime(expires_at_value)
            if expires_at > datetime.now(timezone.utc) + timedelta(minutes=5):
                return connection_row["access_token"], os.environ["ZOHO_API_DOMAIN"], False
        except ValueError:
            logger.warning("Stored token expiry could not be parsed; refreshing token")

    refresh_token = connection_row.get("refresh_token")
    if not refresh_token:
        raise DiscoveryError("REFRESH_TOKEN_MISSING", "Reconnect Zoho CRM")

    try:
        response = requests.post(
            f"{os.environ['ZOHO_ACCOUNTS_URL']}/oauth/v2/token",
            data={
                "grant_type": "refresh_token",
                "client_id": os.environ["ZOHO_CLIENT_ID"],
                "client_secret": os.environ["ZOHO_CLIENT_SECRET"],
                "refresh_token": refresh_token,
            },
            timeout=15,
        )
        response.raise_for_status()
        token_data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise DiscoveryError("TOKEN_REFRESH_FAILED", "Zoho token refresh failed") from exc

    if token_data.get("error") or not token_data.get("access_token"):
        raise DiscoveryError("TOKEN_REFRESH_FAILED", "Zoho token refresh failed")

    expires_in = int(token_data.get("expires_in", 3600))
    datastore.table("zoho_connections").update_row(
        {
            "ROWID": connection_row["ROWID"],
            "access_token": token_data["access_token"],
            "token_expires_at": to_catalyst_datetime(
                datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            ),
        }
    )
    return (
        token_data["access_token"],
        token_data.get("api_domain") or os.environ["ZOHO_API_DOMAIN"],
        True,
    )
