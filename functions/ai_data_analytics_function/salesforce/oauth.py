"""Salesforce OAuth consent, callback, and connection persistence."""

import base64
import hashlib
import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests
import zcatalyst_sdk
from flask import Request, make_response, redirect

from common.core import (
    STATE_TTL_MINUTES,
    from_catalyst_datetime,
    get_current_user,
    get_current_user_id,
    json_response,
    to_catalyst_column_datetime,
    to_catalyst_datetime,
    with_fragment_parameter,
)
from connections.activation import activate_exclusive_connection

logger = logging.getLogger(__name__)

SALESFORCE_CONNECTIONS_TABLE = "salesforce_connections"
SALESFORCE_SCOPE = "api refresh_token id"
DEFAULT_ACCESS_TOKEN_SECONDS = 7200


def _escape_zcql(value):
    return str(value).replace("'", "''")


def _is_true(value):
    return value is True or str(value).strip().lower() == "true"


def _absolute_https_url(name: str) -> str:
    value = str(os.environ.get(name) or "").strip().rstrip("/")
    if not value.startswith("https://"):
        raise RuntimeError(
            f"{name} must be an absolute HTTPS URL"
        )
    return value


def _login_url():
    return _absolute_https_url("SALESFORCE_LOGIN_URL")


def _redirect_uri():
    return _absolute_https_url("SALESFORCE_REDIRECT_URI")


def _generate_pkce_pair():
    """RFC 7636 S256: random code_verifier and BASE64URL(SHA256(verifier))."""
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def start_salesforce_consent(request: Request, datastore):
    try:
        login_url = _login_url()
        redirect_uri = _redirect_uri()
        client_id = os.environ["SALESFORCE_CLIENT_ID"]
    except (KeyError, RuntimeError) as exc:
        logger.exception("Salesforce OAuth is not configured: %s", exc)
        return json_response(
            {
                "error": {
                    "code": "SALESFORCE_OAUTH_CONFIG",
                    "message": "Salesforce OAuth is not configured",
                }
            },
            500,
        )

    user_id = get_current_user_id(request)

    state = secrets.token_urlsafe(32)
    code_verifier, code_challenge = _generate_pkce_pair()
    expires_at = to_catalyst_datetime(
        datetime.now(timezone.utc) + timedelta(minutes=STATE_TTL_MINUTES)
    )

    datastore.table("oauth_states").insert_row(
        {
            "state": state,
            "user_id": user_id,
            "redirect_path": request.args.get("redirect_path", "/setup"),
            "code_verifier": code_verifier,
            "expires_at": expires_at,
        }
    )

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": SALESFORCE_SCOPE,
        "state": state,
        "prompt": "consent",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    query = "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())
    return redirect(f"{login_url}/services/oauth2/authorize?{query}")


def handle_salesforce_callback(request: Request, datastore):
    zcql = zcatalyst_sdk.initialize().zcql()
    frontend_url = os.environ["FRONTEND_SETUP_URL"]

    state = request.args.get("state")
    error = request.args.get("error")

    state_rows = zcql.execute_query(
        "select * from oauth_states where "
        f"state = '{_escape_zcql(state or '')}' limit 1"
    )
    if not state_rows:
        return redirect(
            with_fragment_parameter(frontend_url, "salesforce_error", "invalid_state")
        )

    state_row = state_rows[0]["oauth_states"]
    expires_at = from_catalyst_datetime(state_row["expires_at"])
    if datetime.now(timezone.utc) > expires_at or state_row.get("consumed_at"):
        return redirect(
            with_fragment_parameter(frontend_url, "salesforce_error", "expired_state")
        )

    user_id = state_row["user_id"]
    if str(get_current_user_id(request)) != str(user_id):
        return redirect(
            with_fragment_parameter(
                frontend_url, "salesforce_error", "state_user_mismatch"
            )
        )

    datastore.table("oauth_states").update_row(
        {
            "ROWID": state_row["ROWID"],
            "consumed_at": to_catalyst_datetime(datetime.now(timezone.utc)),
        }
    )

    if error:
        return redirect(
            with_fragment_parameter(
                frontend_url, "salesforce_error", "SALESFORCE_CONSENT_DECLINED"
            )
        )

    code = request.args.get("code")
    code_verifier = str(state_row.get("code_verifier") or "")
    try:
        tokens = exchange_code_for_tokens(code, code_verifier)
        instance_url = str(tokens.get("instance_url") or "").rstrip("/")
        identity_url = str(tokens.get("id") or "")
        if not tokens.get("access_token") or not tokens.get("refresh_token"):
            raise RuntimeError("Salesforce token response is missing tokens")
        if not instance_url:
            raise RuntimeError("Salesforce token response is missing instance_url")
        identity = fetch_salesforce_identity(tokens["access_token"], identity_url)
        if not identity.get("user_id") or not identity.get("organization_id"):
            raise RuntimeError("Salesforce account identity is incomplete")
    except Exception as exc:  # noqa: BLE001 - preserve any prior connection
        logger.exception("Salesforce connection attempt failed for user %s: %s", user_id, exc)
        return redirect(
            with_fragment_parameter(frontend_url, "salesforce_error", "connection_failed")
        )

    expires_in = int(tokens.get("expires_in") or DEFAULT_ACCESS_TOKEN_SECONDS)
    token_expires_at = to_catalyst_datetime(
        datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    )

    upsert_salesforce_connection(
        datastore,
        user_id,
        {
            "salesforce_org_id": identity["organization_id"],
            "organization_name": identity["organization_name"],
            "salesforce_user_id": identity["user_id"],
            "connected_email": identity["email"],
            "connected_name": identity["full_name"],
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "token_expires_at": token_expires_at,
            "instance_url": instance_url,
            "identity_url": identity_url,
            "scope": tokens.get("scope", SALESFORCE_SCOPE),
            "status": "connected",
            "last_error": "",
            "is_active": True,
            "last_selected_at": to_catalyst_column_datetime(datetime.now(timezone.utc)),
        },
    )

    return redirect(with_fragment_parameter(frontend_url, "salesforce_connected", "1"))


def exchange_code_for_tokens(code: str, code_verifier: str) -> dict:
    if not code:
        raise RuntimeError("Salesforce authorization code is missing")
    if not code_verifier:
        raise RuntimeError("Salesforce PKCE code_verifier is missing")
    resp = requests.post(
        f"{_login_url()}/services/oauth2/token",
        data={
            "grant_type": "authorization_code",
            "client_id": os.environ["SALESFORCE_CLIENT_ID"],
            "client_secret": os.environ["SALESFORCE_CLIENT_SECRET"],
            "redirect_uri": _redirect_uri(),
            "code": code,
            "code_verifier": code_verifier,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("error"):
        raise RuntimeError(
            f"Salesforce token exchange failed: {data.get('error_description') or data['error']}"
        )
    return data


def _identity_text(payload: dict, key: str) -> str:
    value = payload.get(key)
    if value is None:
        return ""
    return str(value).strip()


def fetch_salesforce_identity(access_token: str, identity_url: str) -> dict:
    """Read user/org identity from the token `id` URL, with a path fallback.

    Salesforce Identity URL JSON fields used here: user_id, organization_id,
    display_name, first_name, last_name, email, username. The Identity URL
    response does not include organization_name.
    """
    parsed = _identity_from_url(identity_url)
    if not identity_url:
        return parsed

    try:
        response = requests.get(
            identity_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
            params={"format": "json"},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError, TypeError) as exc:
        logger.warning("Salesforce identity request failed; using token id URL: %s", exc)
        return parsed

    if not isinstance(payload, dict):
        return parsed

    # Identity URL JSON: display_name is the full name; first_name/last_name
    # are documented fallbacks. username is the Salesforce login, not org name.
    full_name = _identity_text(payload, "display_name")
    if not full_name:
        full_name = " ".join(
            part
            for part in (
                _identity_text(payload, "first_name"),
                _identity_text(payload, "last_name"),
            )
            if part
        )
    if not full_name:
        full_name = _identity_text(payload, "username")

    email = _identity_text(payload, "email")
    if not email:
        email = _identity_text(payload, "username")

    return {
        "user_id": _identity_text(payload, "user_id") or parsed["user_id"],
        "organization_id": (
            _identity_text(payload, "organization_id") or parsed["organization_id"]
        ),
        "organization_name": _identity_text(payload, "organization_name"),
        "email": email,
        "full_name": full_name,
    }


def _identity_from_url(identity_url: str) -> dict:
    path_parts = [part for part in urlparse(identity_url or "").path.split("/") if part]
    organization_id = ""
    user_id = ""
    if len(path_parts) >= 3 and path_parts[0] == "id":
        organization_id = path_parts[1]
        user_id = path_parts[2]
    return {
        "user_id": user_id,
        "organization_id": organization_id,
        "organization_name": "",
        "email": "",
        "full_name": "",
    }


def upsert_salesforce_connection(datastore, user_id: str, fields: dict):
    zcql = zcatalyst_sdk.initialize().zcql()
    table = datastore.table(SALESFORCE_CONNECTIONS_TABLE)

    existing = zcql.execute_query(
        f"select * from {SALESFORCE_CONNECTIONS_TABLE} where "
        f"user_id = '{_escape_zcql(user_id)}'"
    )
    existing_rows = [item[SALESFORCE_CONNECTIONS_TABLE] for item in existing]
    target = next(
        (
            row
            for row in existing_rows
            if str(row.get("salesforce_org_id") or "") == str(fields["salesforce_org_id"])
            and (
                str(row.get("salesforce_user_id") or "") == str(fields["salesforce_user_id"])
                or (
                    not row.get("salesforce_user_id")
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
    activate_exclusive_connection(
        datastore, zcql, user_id, SALESFORCE_CONNECTIONS_TABLE, selected_row_id
    )
    return selected


def find_active_salesforce_connection(zcql, user_id: str):
    results = zcql.execute_query(
        f"select * from {SALESFORCE_CONNECTIONS_TABLE} where "
        f"user_id = '{_escape_zcql(user_id)}' and status = 'connected'"
    )
    rows = [item[SALESFORCE_CONNECTIONS_TABLE] for item in results]
    active = [row for row in rows if _is_true(row.get("is_active"))]
    if not active:
        return None
    active.sort(
        key=lambda row: (
            str(row.get("last_selected_at") or ""),
            str(row.get("ROWID") or ""),
        ),
        reverse=True,
    )
    return active[0]


def find_connected_salesforce_connection(zcql, user_id: str):
    """Return a connected Salesforce row for listing. is_active is preference, not a filter."""
    results = zcql.execute_query(
        f"select * from {SALESFORCE_CONNECTIONS_TABLE} where "
        f"user_id = '{_escape_zcql(user_id)}' and status = 'connected'"
    )
    rows = [item[SALESFORCE_CONNECTIONS_TABLE] for item in results]
    if not rows:
        return None
    rows.sort(
        key=lambda row: (
            _is_true(row.get("is_active")),
            str(row.get("last_selected_at") or ""),
            str(row.get("ROWID") or ""),
        ),
        reverse=True,
    )
    return rows[0]


def get_salesforce_connection(request: Request, datastore):
    zcql = zcatalyst_sdk.initialize().zcql()
    user = get_current_user()
    user_id = str(user["user_id"])

    row = find_connected_salesforce_connection(zcql, user_id)
    if not row:
        return make_response(json.dumps(None), 200, {"Content-Type": "application/json"})

    all_rows = zcql.execute_query(
        f"select * from {SALESFORCE_CONNECTIONS_TABLE} where "
        f"user_id = '{_escape_zcql(user_id)}' and status = 'connected'"
    )
    available_connections = [
        {
            "connectionId": str(item[SALESFORCE_CONNECTIONS_TABLE]["ROWID"]),
            "organizationId": str(
                item[SALESFORCE_CONNECTIONS_TABLE].get("salesforce_org_id") or ""
            ),
            "organizationName": str(
                item[SALESFORCE_CONNECTIONS_TABLE].get("organization_name") or ""
            ),
            "name": str(item[SALESFORCE_CONNECTIONS_TABLE].get("connected_name") or ""),
            "email": str(item[SALESFORCE_CONNECTIONS_TABLE].get("connected_email") or ""),
            "instanceUrl": str(
                item[SALESFORCE_CONNECTIONS_TABLE].get("instance_url") or ""
            ),
            "isActive": _is_true(item[SALESFORCE_CONNECTIONS_TABLE].get("is_active")),
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
        "provider": "salesforce",
        "organizationId": row.get("salesforce_org_id", ""),
        "organizationName": row.get("organization_name", ""),
        "instanceUrl": row.get("instance_url", ""),
        "isActive": _is_true(row.get("is_active")),
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
        "availableConnections": available_connections,
    }
    return make_response(json.dumps(connection), 200, {"Content-Type": "application/json"})


def activate_salesforce_connection(request: Request, datastore, connection_row_id: str):
    """Select an existing Salesforce connection without repeating consent."""
    if not str(connection_row_id).isdigit():
        return make_response("Not found", 404)

    user_id = get_current_user_id(request)
    zcql = zcatalyst_sdk.initialize().zcql()
    rows = zcql.execute_query(
        f"select * from {SALESFORCE_CONNECTIONS_TABLE} where "
        f"ROWID = {connection_row_id} "
        f"and user_id = '{_escape_zcql(user_id)}' "
        "and status = 'connected' limit 1"
    )
    if not rows:
        return make_response("Not found", 404)

    selected = rows[0][SALESFORCE_CONNECTIONS_TABLE]
    try:
        activate_exclusive_connection(
            datastore,
            zcql,
            user_id,
            SALESFORCE_CONNECTIONS_TABLE,
            selected["ROWID"],
        )
    except Exception:
        logger.exception(
            "Salesforce connection activation failed for user %s", user_id
        )
        return json_response(
            {
                "error": {
                    "code": "CONNECTION_ACTIVATION_FAILED",
                    "message": "The connection could not be selected",
                }
            },
            500,
        )
    return get_salesforce_connection(request, datastore)
