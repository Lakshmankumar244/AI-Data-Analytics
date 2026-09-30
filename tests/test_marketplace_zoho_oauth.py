import json
import re
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


FUNCTION_ROOT = (
    Path(__file__).resolve().parents[1]
    / "functions"
    / "ai_data_analytics_function"
)
sys.path.insert(0, str(FUNCTION_ROOT))

if "flask" not in sys.modules:
    flask = types.ModuleType("flask")
    flask.Request = type("Request", (), {})

    class FakeFlaskResponse:
        def __init__(self, payload, status=200, headers=None):
            self.payload = payload
            self.status_code = status
            self.headers = headers or {}

    flask.make_response = lambda payload, status=200, headers=None: FakeFlaskResponse(
        payload, status, headers
    )
    flask.redirect = lambda location: location
    sys.modules["flask"] = flask

if "zcatalyst_sdk" not in sys.modules:
    zcatalyst_sdk = types.ModuleType("zcatalyst_sdk")
    zcatalyst_sdk.initialize = lambda: None
    sys.modules["zcatalyst_sdk"] = zcatalyst_sdk

from common.core import AuthenticationRequired, to_catalyst_datetime
from connections.marketplace import persist_marketplace_zoho_oauth_connection
from connections.routes import (
    MARKETPLACE_ENTRY_COOKIE,
    MARKETPLACE_OAUTH_STATE_MARK,
    enter_marketplace,
    handle_callback,
    marketplace_frontend_return_url,
    start_consent,
    start_marketplace_consent,
    upsert_connection,
)
from installations.repository import INSTALLATIONS_TABLE, MEMBERS_TABLE


CREDENTIAL_KEYS = (
    "access_token",
    "refresh_token",
    "client_secret",
    "client_id",
    "code",
    "Authorization",
)


def _quoted(query, column):
    match = re.search(rf"{re.escape(column)} = '((?:[^']|'')*)'", query)
    if not match:
        return None
    return match.group(1).replace("''", "'")


class MemoryTable:
    def __init__(self, store, name):
        self.store = store
        self.name = name

    def insert_row(self, row):
        stored = dict(row)
        stored.setdefault("ROWID", str(self.store.next_id))
        self.store.next_id += 1
        self.store.rows.setdefault(self.name, []).append(stored)
        return dict(stored)

    def update_row(self, row):
        row_id = str(row["ROWID"])
        for existing in self.store.rows[self.name]:
            if str(existing["ROWID"]) == row_id:
                existing.update(row)
                return dict(existing)
        raise KeyError(row_id)


class MemoryStore:
    def __init__(self):
        self.next_id = 100
        self.rows = {
            INSTALLATIONS_TABLE: [],
            MEMBERS_TABLE: [],
            "zoho_connections": [],
            "oauth_states": [],
        }

    def table(self, name):
        self.rows.setdefault(name, [])
        return MemoryTable(self, name)

    def zcql(self):
        return self

    def execute_query(self, query):
        if f"from {INSTALLATIONS_TABLE}" in query:
            matches = list(self.rows[INSTALLATIONS_TABLE])
            org_id = _quoted(query, "zoho_org_id")
            source = _quoted(query, "source")
            if org_id is not None:
                matches = [row for row in matches if str(row.get("zoho_org_id") or "") == org_id]
            if source is not None:
                matches = [row for row in matches if str(row.get("source") or "") == source]
            if "limit 1" in query:
                matches = matches[:1]
            return [{INSTALLATIONS_TABLE: dict(row)} for row in matches]
        if f"from {MEMBERS_TABLE}" in query:
            matches = list(self.rows[MEMBERS_TABLE])
            installation_id = _quoted(query, "installation_id")
            user_id = _quoted(query, "catalyst_user_id")
            if installation_id is not None:
                matches = [
                    row
                    for row in matches
                    if str(row.get("installation_id") or "") == installation_id
                ]
            if user_id is not None:
                matches = [
                    row
                    for row in matches
                    if str(row.get("catalyst_user_id") or "") == user_id
                ]
            if "limit 1" in query:
                matches = matches[:1]
            return [{MEMBERS_TABLE: dict(row)} for row in matches]
        if "from zoho_connections" in query:
            matches = list(self.rows["zoho_connections"])
            user_id = _quoted(query, "user_id")
            if user_id is not None:
                matches = [
                    row for row in matches if str(row.get("user_id") or "") == user_id
                ]
            return [{"zoho_connections": dict(row)} for row in matches]
        if "from oauth_states" in query:
            matches = list(self.rows["oauth_states"])
            state = _quoted(query, "state")
            if state is not None:
                matches = [row for row in matches if str(row.get("state") or "") == state]
            if "limit 1" in query:
                matches = matches[:1]
            return [{"oauth_states": dict(row)} for row in matches]
        raise AssertionError(f"unexpected query: {query}")


def _organization():
    return {"id": "800612345", "company_name": "Acme CRM", "time_zone": "UTC"}


def _profile():
    return {"user_id": "zuid-1", "email": "owner@example.com", "full_name": "Owner"}


def _connection_fields():
    return {
        "zoho_org_id": "800612345",
        "organization_name": "Acme CRM",
        "zoho_user_id": "zuid-1",
        "connected_email": "owner@example.com",
        "connected_name": "Owner",
        "access_token": "zoho-access-secret",
        "refresh_token": "zoho-refresh-secret",
        "token_expires_at": "2026-09-20 12:00:00:000",
        "scope": "ZohoCRM.modules.READ",
        "status": "connected",
        "last_error": "",
        "accessible_modules": "[]",
        "is_active": True,
    }


def _assert_no_credentials(rows):
    for row in rows:
        for key in CREDENTIAL_KEYS:
            if key in row:
                raise AssertionError(f"credential {key} written to {row}")


class FakeRequest:
    def __init__(self, args=None):
        self.args = args or {}


class MarketplaceZohoOAuthTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()

    def test_marketplace_persist_creates_installation_and_sets_connection_installation_id(self):
        result = persist_marketplace_zoho_oauth_connection(
            self.store,
            self.store,
            "user-1",
            _organization(),
            _profile(),
            _connection_fields(),
        )
        self.assertTrue(result["created_installation"])
        self.assertTrue(result["created_member"])
        connection = result["connection"]
        self.assertEqual(connection["installation_id"], result["installation_id"])
        self.assertEqual(connection["user_id"], "user-1")
        self.assertEqual(connection["access_token"], "zoho-access-secret")
        self.assertEqual(len(self.store.rows["zoho_connections"]), 1)
        _assert_no_credentials(self.store.rows[INSTALLATIONS_TABLE])
        _assert_no_credentials(self.store.rows[MEMBERS_TABLE])

    def test_marketplace_persist_reuses_installation_membership_and_connection(self):
        first = persist_marketplace_zoho_oauth_connection(
            self.store, self.store, "user-1", _organization(), _profile(), _connection_fields()
        )
        second_fields = _connection_fields()
        second_fields["access_token"] = "zoho-access-rotated"
        second = persist_marketplace_zoho_oauth_connection(
            self.store, self.store, "user-1", _organization(), _profile(), second_fields
        )
        self.assertFalse(second["created_installation"])
        self.assertFalse(second["created_member"])
        self.assertEqual(second["installation_id"], first["installation_id"])
        self.assertEqual(second["connection"]["ROWID"], first["connection"]["ROWID"])
        self.assertEqual(second["connection"]["access_token"], "zoho-access-rotated")
        self.assertEqual(len(self.store.rows[INSTALLATIONS_TABLE]), 1)
        self.assertEqual(len(self.store.rows[MEMBERS_TABLE]), 1)
        self.assertEqual(len(self.store.rows["zoho_connections"]), 1)

    def test_does_not_backfill_standalone_connection(self):
        standalone = {
            "ROWID": "50",
            "user_id": "user-1",
            "zoho_org_id": "800612345",
            "zoho_user_id": "zuid-1",
            "connected_email": "owner@example.com",
            "access_token": "standalone-access",
            "refresh_token": "standalone-refresh",
            "status": "connected",
            "is_active": True,
        }
        self.store.rows["zoho_connections"].append(standalone)
        result = persist_marketplace_zoho_oauth_connection(
            self.store, self.store, "user-1", _organization(), _profile(), _connection_fields()
        )
        self.assertEqual(len(self.store.rows["zoho_connections"]), 2)
        leftover = next(
            row for row in self.store.rows["zoho_connections"] if row["ROWID"] == "50"
        )
        self.assertNotIn("installation_id", leftover)
        self.assertEqual(leftover["access_token"], "standalone-access")
        marketplace = next(
            row
            for row in self.store.rows["zoho_connections"]
            if row["ROWID"] != "50"
        )
        self.assertEqual(marketplace["installation_id"], result["installation_id"])
        self.assertFalse(leftover.get("is_active") is True)

    def test_standalone_upsert_still_omits_installation_id(self):
        with patch("connections.routes.zcatalyst_sdk") as sdk:
            sdk.initialize.return_value.zcql.return_value = self.store
            upsert_connection(self.store, "user-1", _connection_fields())
        inserted = self.store.rows["zoho_connections"][0]
        self.assertNotIn("installation_id", inserted)
        self.assertEqual(len(self.store.rows[INSTALLATIONS_TABLE]), 0)
        self.assertEqual(len(self.store.rows[MEMBERS_TABLE]), 0)

    def test_marketplace_consent_marks_state_standalone_does_not(self):
        env = {
            "ZOHO_ACCOUNTS_URL": "https://accounts.zoho.in",
            "ZOHO_CLIENT_ID": "client-id",
            "ZOHO_REDIRECT_URI": "https://example.test/api/zoho/callback",
        }
        with patch.dict("os.environ", env, clear=False):
            with patch("connections.routes.get_current_user_id", return_value="user-1"):
                with patch("connections.routes.redirect", side_effect=lambda url: url):
                    start_consent(FakeRequest(), self.store)
                    start_marketplace_consent(FakeRequest(), self.store)
        standalone_state = self.store.rows["oauth_states"][0]
        marketplace_state = self.store.rows["oauth_states"][1]
        self.assertEqual(standalone_state["redirect_path"], "/setup")
        self.assertEqual(
            marketplace_state["redirect_path"], MARKETPLACE_OAUTH_STATE_MARK
        )

    def test_marketplace_consent_requires_catalyst_user_and_ignores_client_ids(self):
        env = {
            "ZOHO_ACCOUNTS_URL": "https://accounts.zoho.in",
            "ZOHO_CLIENT_ID": "client-id",
            "ZOHO_REDIRECT_URI": "https://example.test/api/zoho/callback",
        }
        forged = FakeRequest(
            {
                "org_id": "forged-org",
                "user_id": "forged-user",
                "redirect_path": "/setup",
            }
        )
        with patch.dict("os.environ", env, clear=False):
            with patch(
                "connections.routes.get_current_user_id",
                side_effect=AuthenticationRequired("Sign in required"),
            ):
                with self.assertRaises(AuthenticationRequired):
                    start_marketplace_consent(forged, self.store)
        self.assertEqual(self.store.rows["oauth_states"], [])

        with patch.dict("os.environ", env, clear=False):
            with patch("connections.routes.get_current_user_id", return_value="user-1"):
                with patch("connections.routes.redirect", side_effect=lambda url: url):
                    start_marketplace_consent(forged, self.store)
        state = self.store.rows["oauth_states"][0]
        self.assertEqual(state["user_id"], "user-1")
        self.assertEqual(state["redirect_path"], MARKETPLACE_OAUTH_STATE_MARK)
        encoded = json.dumps(state)
        self.assertNotIn("forged-org", encoded)
        self.assertNotIn("forged-user", encoded)

    def test_marketplace_frontend_return_url_targets_react_app(self):
        self.assertEqual(
            marketplace_frontend_return_url("https://example.test"),
            "https://example.test/app/?source=marketplace",
        )
        self.assertEqual(
            marketplace_frontend_return_url("https://example.test/"),
            "https://example.test/app/?source=marketplace",
        )
        self.assertEqual(
            marketplace_frontend_return_url("https://example.test/app"),
            "https://example.test/app/?source=marketplace",
        )
        self.assertEqual(
            marketplace_frontend_return_url("https://example.test/app/"),
            "https://example.test/app/?source=marketplace",
        )

    def test_marketplace_enter_sets_cookie_and_ignores_client_ids(self):
        env = {"FRONTEND_SETUP_URL": "https://example.test"}
        forged = FakeRequest({"org_id": "forged-org", "user_id": "forged-user"})
        with patch.dict("os.environ", env, clear=False):
            with patch(
                "connections.routes.get_current_user_id",
                side_effect=AuthenticationRequired("Sign in required"),
            ):
                unauthenticated = enter_marketplace(forged)
            with patch("connections.routes.get_current_user_id", return_value="user-1"):
                authenticated = enter_marketplace(forged)
        self.assertIn(
            f"{MARKETPLACE_ENTRY_COOKIE}=1",
            unauthenticated.headers["Set-Cookie"],
        )
        self.assertIn("/__catalyst/auth/login", unauthenticated.payload)
        self.assertNotIn("forged-org", unauthenticated.payload)
        self.assertNotIn("forged-user", unauthenticated.payload)
        self.assertIn("/app/?source=marketplace", authenticated.payload)
        self.assertIn(
            f"{MARKETPLACE_ENTRY_COOKIE}=1",
            authenticated.headers["Set-Cookie"],
        )

    def _run_callback(self, redirect_path, extra_args=None):
        expires = to_catalyst_datetime(datetime.now(timezone.utc) + timedelta(minutes=5))
        self.store.table("oauth_states").insert_row(
            {
                "state": "state-1",
                "user_id": "user-1",
                "redirect_path": redirect_path,
                "expires_at": expires,
            }
        )
        args = {"state": "state-1", "code": "auth-code"}
        if extra_args:
            args.update(extra_args)
        request = FakeRequest(args)
        tokens = {
            "access_token": "zoho-access-secret",
            "refresh_token": "zoho-refresh-secret",
            "expires_in": 3600,
            "api_domain": "https://www.zohoapis.in",
        }
        env = {
            "FRONTEND_SETUP_URL": "https://example.test",
            "ZOHO_API_DOMAIN": "https://www.zohoapis.in",
        }
        with patch.dict("os.environ", env, clear=False):
            with patch("connections.routes.zcatalyst_sdk") as sdk:
                sdk.initialize.return_value.zcql.return_value = self.store
                with patch("connections.routes.get_current_user_id", return_value="user-1"):
                    with patch(
                        "connections.routes.exchange_code_for_tokens", return_value=tokens
                    ):
                        with patch(
                            "connections.routes.fetch_zoho_profile", return_value=_profile()
                        ):
                            with patch(
                                "connections.routes.fetch_organization_metadata",
                                return_value=_organization(),
                            ):
                                with patch(
                                    "connections.routes.fetch_accessible_modules",
                                    return_value=[{"api_name": "Leads"}],
                                ):
                                    with patch(
                                        "connections.routes.redirect",
                                        side_effect=lambda url: url,
                                    ):
                                        return handle_callback(request, self.store)

    def test_marketplace_callback_links_connection_to_installation(self):
        location = self._run_callback(
            MARKETPLACE_OAUTH_STATE_MARK,
            extra_args={"org_id": "forged-org", "user_id": "forged-user"},
        )
        self.assertIn("zoho_connected", location)
        self.assertIn("/app/", location)
        self.assertIn("source=marketplace", location)
        self.assertNotIn("forged-org", location)
        self.assertNotIn("forged-user", location)
        self.assertEqual(len(self.store.rows[INSTALLATIONS_TABLE]), 1)
        self.assertEqual(len(self.store.rows[MEMBERS_TABLE]), 1)
        connection = self.store.rows["zoho_connections"][0]
        self.assertEqual(
            connection["installation_id"],
            self.store.rows[INSTALLATIONS_TABLE][0]["ROWID"],
        )
        self.assertEqual(connection["user_id"], "user-1")
        self.assertEqual(json.loads(connection["accessible_modules"])[0]["api_name"], "Leads")
        _assert_no_credentials(self.store.rows[INSTALLATIONS_TABLE])
        _assert_no_credentials(self.store.rows[MEMBERS_TABLE])

    def test_standalone_callback_does_not_create_installation(self):
        location = self._run_callback("/setup")
        self.assertIn("zoho_connected", location)
        self.assertTrue(location.startswith("https://example.test"))
        self.assertNotIn("source=marketplace", location)
        self.assertNotIn("/app/", location)
        self.assertEqual(self.store.rows[INSTALLATIONS_TABLE], [])
        self.assertEqual(self.store.rows[MEMBERS_TABLE], [])
        connection = self.store.rows["zoho_connections"][0]
        self.assertNotIn("installation_id", connection)
        self.assertEqual(connection["user_id"], "user-1")
        self.assertEqual(connection["access_token"], "zoho-access-secret")


if __name__ == "__main__":
    unittest.main()
