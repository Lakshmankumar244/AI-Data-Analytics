"""OAuth routes, connection persistence, and token refresh."""

import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

import requests
import zcatalyst_sdk
from flask import Request, make_response, redirect

from common.core import (
    DiscoveryError,
    STATE_TTL_MINUTES,
    ZOHO_SCOPE,
    from_catalyst_datetime,
    get_current_user,
    get_current_user_id,
    to_catalyst_column_datetime,
    to_catalyst_datetime,
    with_fragment_parameter,
)
from connections.repository import find_active_connection
from zoho.client import fetch_accessible_modules, fetch_organization_metadata

logger = logging.getLogger(__name__)

LEGACY_DEVELOPMENT_USER_ID = "dev-user-1"


def _escape_zcql(value):
    return str(value).replace("'", "''")


def migrate_legacy_connection(datastore, user):
    """Claim the single legacy development row only for the matching user email."""
    user_id = str(user["user_id"])
    user_email = str(user.get("email_id") or "").strip().lower()
    zcql = zcatalyst_sdk.initialize().zcql()
    existing = zcql.execute_query(
        "select ROWID from zoho_connections where "
        f"user_id = '{_escape_zcql(user_id)}' limit 1"
    )
    if existing:
        return False

    legacy = zcql.execute_query(
        "select * from zoho_connections where "
        f"user_id = '{LEGACY_DEVELOPMENT_USER_ID}'"
    )
    if len(legacy) != 1:
        return False
    legacy_row = legacy[0]["zoho_connections"]
    legacy_email = str(legacy_row.get("connected_email") or "").strip().lower()
    if not user_email or not legacy_email or user_email != legacy_email:
        logger.warning(
            "Legacy connection migration skipped because authenticated and Zoho emails differ"
        )
        return False

    datastore.table("zoho_connections").update_row(
        {"ROWID": legacy_row["ROWID"], "user_id": user_id, "is_active": True}
    )
    logger.info("Migrated legacy development connection to Catalyst user %s", user_id)
    return True

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

def start_consent(request: Request, datastore):
    user_id = get_current_user_id(request)

    state = secrets.token_urlsafe(32)
    expires_at = to_catalyst_datetime(datetime.now(timezone.utc) + timedelta(minutes=STATE_TTL_MINUTES))

    datastore.table("oauth_states").insert_row(
        {
            "state": state,
            "user_id": user_id,
            "redirect_path": request.args.get("redirect_path", "/setup"),
            "expires_at": expires_at,
        }
    )

    accounts_url = os.environ["ZOHO_ACCOUNTS_URL"]
    params = {
        "scope": ZOHO_SCOPE,
        "client_id": os.environ["ZOHO_CLIENT_ID"],
        "response_type": "code",
        "access_type": "offline",  # required to get a refresh_token back
        "redirect_uri": os.environ["ZOHO_REDIRECT_URI"],
        "state": state,
        "prompt": "consent",
    }
    query = "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())
    return redirect(f"{accounts_url}/oauth/v2/auth?{query}")


def handle_callback(request: Request, datastore):
    zcql = zcatalyst_sdk.initialize().zcql()
    frontend_url = os.environ["FRONTEND_SETUP_URL"]

    state = request.args.get("state")
    error = request.args.get("error")  # e.g. "access_denied" if the user hit Cancel

    state_rows = zcql.execute_query(
        "select * from oauth_states where "
        f"state = '{_escape_zcql(state or '')}' limit 1"
    )
    if not state_rows:
        # Unknown or replayed state - don't trust this callback.
        return redirect(with_fragment_parameter(frontend_url, "zoho_error", "invalid_state"))

    state_row = state_rows[0]["oauth_states"]
    expires_at = from_catalyst_datetime(state_row["expires_at"])
    if datetime.now(timezone.utc) > expires_at or state_row.get("consumed_at"):
        return redirect(with_fragment_parameter(frontend_url, "zoho_error", "expired_state"))

    user_id = state_row["user_id"]
    if str(get_current_user_id(request)) != str(user_id):
        return redirect(
            with_fragment_parameter(frontend_url, "zoho_error", "state_user_mismatch")
        )

    # Mark the state consumed either way, so it can't be replayed.
    datastore.table("oauth_states").update_row(
        {"ROWID": state_row["ROWID"], "consumed_at": to_catalyst_datetime(datetime.now(timezone.utc))}
    )

    if error:
        # A canceled reconnect/switch must not invalidate a connection that
        # was already working before the user opened the consent screen.
        # Soft outcome for the frontend - matches the ZOHO_CONSENT_DECLINED
        # code that App.jsx's getConnection().catch() already branches on.
        return redirect(
            with_fragment_parameter(frontend_url, "zoho_error", "ZOHO_CONSENT_DECLINED")
        )

    code = request.args.get("code")
    try:
        tokens = exchange_code_for_tokens(code)
        api_domain = tokens.get("api_domain") or os.environ["ZOHO_API_DOMAIN"]
        profile = fetch_zoho_profile(tokens["access_token"], api_domain)
        organization = fetch_organization_metadata(tokens["access_token"], api_domain)
        modules = fetch_accessible_modules(tokens["access_token"], api_domain)
        if not profile.get("user_id") or not organization.get("id"):
            raise RuntimeError("Zoho account identity is incomplete")
    except Exception as exc:  # noqa: BLE001 - surface any failure as a connection error
        logger.exception("Zoho connection attempt failed for user %s: %s", user_id, exc)
        # Preserve a previously working connection if switching accounts fails.
        return redirect(
            with_fragment_parameter(frontend_url, "zoho_error", "connection_failed")
        )

    token_expires_at = (
        to_catalyst_datetime(
    datetime.now(timezone.utc) + timedelta(seconds=tokens["expires_in"]))
    )

    upsert_connection(
        datastore,
        user_id,
        {
            "zoho_org_id": organization["id"],
            "organization_name": organization.get("company_name", ""),
            "zoho_user_id": profile["user_id"],
            "connected_email": profile.get("email", ""),
            "connected_name": profile.get("full_name", ""),
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "token_expires_at": token_expires_at,
            "scope": tokens.get("scope", ZOHO_SCOPE),
            "status": "connected",
            "last_error": "",
            "accessible_modules": json.dumps(modules),
            "modules_synced_at": to_catalyst_datetime(datetime.now(timezone.utc)),
            "is_active": True,
            "last_selected_at": to_catalyst_column_datetime(datetime.now(timezone.utc)),
        },
    )

    return redirect(with_fragment_parameter(frontend_url, "zoho_connected", "1"))


def upsert_connection(datastore, user_id: str, fields: dict):
    zcql = zcatalyst_sdk.initialize().zcql()
    table = datastore.table("zoho_connections")

    existing = zcql.execute_query(
        "select * from zoho_connections where "
        f"user_id = '{_escape_zcql(user_id)}'"
    )
    existing_rows = [item["zoho_connections"] for item in existing]
    target = next(
        (
            row
            for row in existing_rows
            if str(row.get("zoho_org_id") or "") == str(fields["zoho_org_id"])
            and (
                str(row.get("zoho_user_id") or "") == str(fields["zoho_user_id"])
                or (
                    not row.get("zoho_user_id")
                    and str(row.get("connected_email") or "").strip().lower()
                    == str(fields.get("connected_email") or "").strip().lower()
                )
            )
        ),
        None,
    )
    row_data = {"user_id": user_id, **fields}

    if target:
        row_data["ROWID"] = target["ROWID"]
        selected = table.update_row(row_data)
    else:
        selected = table.insert_row(row_data)

    selected_row_id = str(selected["ROWID"])
    for connection in existing_rows:
        if str(connection["ROWID"]) != selected_row_id and (
            connection.get("is_active") is True
            or str(connection.get("is_active") or "").lower() == "true"
        ):
            table.update_row({"ROWID": connection["ROWID"], "is_active": False})
    return selected


def exchange_code_for_tokens(code: str) -> dict:
    accounts_url = os.environ["ZOHO_ACCOUNTS_URL"]
    resp = requests.post(
        f"{accounts_url}/oauth/v2/token",
        data={
            "grant_type": "authorization_code",
            "client_id": os.environ["ZOHO_CLIENT_ID"],
            "client_secret": os.environ["ZOHO_CLIENT_SECRET"],
            "redirect_uri": os.environ["ZOHO_REDIRECT_URI"],
            "code": code,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"Zoho token exchange failed: {data['error']}")
    return data


def fetch_zoho_profile(access_token: str, api_domain: str) -> dict:
    resp = requests.get(
        f"{api_domain}/crm/v6/users?type=CurrentUser",
        headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
        timeout=15,
    )
    resp.raise_for_status()
    user = resp.json()["users"][0]
    return {
        "user_id": user.get("zuid") or user.get("id", ""),
        "email": user.get("email", ""),
        "full_name": user.get("full_name", ""),
    }


def get_connection(request: Request, datastore):
    zcql = zcatalyst_sdk.initialize().zcql()
    user = get_current_user()
    user_id = str(user["user_id"])
    legacy_migrated = migrate_legacy_connection(datastore, user)

    row = find_active_connection(zcql, user_id)
    if not row:
        return make_response(json.dumps(None), 200, {"Content-Type": "application/json"})

    all_rows = zcql.execute_query(
        "select * from zoho_connections where "
        f"user_id = '{_escape_zcql(user_id)}' and status = 'connected'"
    )
    available_connections = [
        {
            "connectionId": str(item["zoho_connections"]["ROWID"]),
            "organizationId": str(item["zoho_connections"].get("zoho_org_id") or ""),
            "organizationName": str(
                item["zoho_connections"].get("organization_name") or ""
            ),
            "name": str(item["zoho_connections"].get("connected_name") or ""),
            "email": str(item["zoho_connections"].get("connected_email") or ""),
        }
        for item in all_rows
    ]
    available_connections.sort(
        key=lambda connection: (
            connection["name"].lower(),
            connection["email"].lower(),
            connection["connectionId"],
        )
    )

    connection = {
        "connectionId": str(row["ROWID"]),
        "organizationId": row.get("zoho_org_id", ""),
        "organizationName": row.get("organization_name", ""),
        "catalystUser": {
            "userId": user_id,
            "name": " ".join(
                part
                for part in (user.get("first_name"), user.get("last_name"))
                if part
            ),
            "email": user.get("email_id", ""),
        },
        "connectedUser": {
            "name": row.get("connected_name", ""),
            "email": row.get("connected_email", ""),
        },
        "accessibleModules": json.loads(row.get("accessible_modules") or "[]"),
        "availableConnections": available_connections,
        "legacyMigrated": legacy_migrated,
    }
    return make_response(json.dumps(connection), 200, {"Content-Type": "application/json"})


def activate_connection(request: Request, datastore, connection_row_id: str):
    """Select an existing connection without repeating Zoho consent."""
    if not str(connection_row_id).isdigit():
        return make_response("Not found", 404)

    user_id = get_current_user_id(request)
    zcql = zcatalyst_sdk.initialize().zcql()
    rows = zcql.execute_query(
        "select * from zoho_connections where "
        f"ROWID = {connection_row_id} "
        f"and user_id = '{_escape_zcql(user_id)}' "
        "and status = 'connected' limit 1"
    )
    if not rows:
        return make_response("Not found", 404)

    table = datastore.table("zoho_connections")
    selected = rows[0]["zoho_connections"]
    table.update_row(
        {
            "ROWID": selected["ROWID"],
            "is_active": True,
            "last_selected_at": to_catalyst_column_datetime(datetime.now(timezone.utc)),
        }
    )
    user_rows = zcql.execute_query(
        "select ROWID,is_active from zoho_connections where "
        f"user_id = '{_escape_zcql(user_id)}'"
    )
    for item in user_rows:
        connection = item["zoho_connections"]
        if str(connection["ROWID"]) != str(selected["ROWID"]) and (
            connection.get("is_active") is True
            or str(connection.get("is_active") or "").lower() == "true"
        ):
            table.update_row({"ROWID": connection["ROWID"], "is_active": False})
    return get_connection(request, datastore)
