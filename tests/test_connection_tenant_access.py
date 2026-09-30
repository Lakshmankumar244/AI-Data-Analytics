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

        def get_json(self, silent=True):
            del silent
            if isinstance(self.payload, (bytes, bytearray)):
                return json.loads(self.payload.decode("utf-8"))
            if isinstance(self.payload, str):
                return json.loads(self.payload)
            return self.payload

    flask.make_response = lambda payload, status=200, headers=None: FakeFlaskResponse(
        payload, status, headers
    )
    flask.redirect = lambda location: location
    sys.modules["flask"] = flask

if "zcatalyst_sdk" not in sys.modules:
    zcatalyst_sdk = types.ModuleType("zcatalyst_sdk")
    zcatalyst_sdk.initialize = lambda: None
    sys.modules["zcatalyst_sdk"] = zcatalyst_sdk

from analytics.repository import find_owned_scan
from common.core import to_catalyst_datetime
from connections.repository import find_scan_connection
from connections.routes import (
    MARKETPLACE_OAUTH_STATE_MARK,
    activate_connection,
    get_connection,
    handle_callback,
    start_consent,
    upsert_connection,
)
from installations.authorization import list_accessible_connected_connections
from installations.repository import (
    INSTALLATIONS_TABLE,
    MEMBERS_TABLE,
    SALESFORCE_CONNECTIONS_TABLE,
    SOURCE_MARKETPLACE,
    STATUS_ACTIVE,
    ZOHO_CONNECTIONS_TABLE,
)
from salesforce.discovery import _select_salesforce_connection
from salesforce.oauth import activate_salesforce_connection, get_salesforce_connection


def _quoted(query, column):
    match = re.search(
        rf"(?<![A-Za-z0-9_]){re.escape(column)} = '((?:[^']|'')*)'", query
    )
    if not match:
        return None
    return match.group(1).replace("''", "'")


def _rowid_equals(query):
    match = re.search(r"ROWID = (\d+)", query)
    return match.group(1) if match else None


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
            ZOHO_CONNECTIONS_TABLE: [],
            SALESFORCE_CONNECTIONS_TABLE: [],
            "oauth_states": [],
            "scan_jobs": [],
        }

    def table(self, name):
        self.rows.setdefault(name, [])
        return MemoryTable(self, name)

    def add(self, table, row):
        stored = dict(row)
        self.rows.setdefault(table, []).append(stored)
        return stored

    def zcql(self):
        return self

    def execute_query(self, query):
        table = None
        for name in (
            INSTALLATIONS_TABLE,
            MEMBERS_TABLE,
            ZOHO_CONNECTIONS_TABLE,
            SALESFORCE_CONNECTIONS_TABLE,
            "oauth_states",
            "scan_jobs",
        ):
            if f"from {name}" in query:
                table = name
                break
        if table is None:
            raise AssertionError(f"unexpected query: {query}")
        matches = list(self.rows[table])
        row_id = _rowid_equals(query)
        if row_id is not None:
            matches = [row for row in matches if str(row.get("ROWID") or "") == row_id]
        user_id = _quoted(query, "user_id")
        if user_id is not None:
            matches = [row for row in matches if str(row.get("user_id") or "") == user_id]
        catalyst_user_id = _quoted(query, "catalyst_user_id")
        if catalyst_user_id is not None:
            matches = [
                row
                for row in matches
                if str(row.get("catalyst_user_id") or "") == catalyst_user_id
            ]
        installation_id = _quoted(query, "installation_id")
        if installation_id is not None:
            matches = [
                row
                for row in matches
                if str(row.get("installation_id") or "") == installation_id
            ]
        scan_id = _quoted(query, "scan_id")
        if scan_id is not None:
            matches = [row for row in matches if str(row.get("scan_id") or "") == scan_id]
        state = _quoted(query, "state")
        if state is not None:
            matches = [row for row in matches if str(row.get("state") or "") == state]
        if "status = 'connected'" in query:
            matches = [
                row for row in matches if str(row.get("status") or "") == "connected"
            ]
        if "limit 1" in query:
            matches = matches[:1]
        return [{table: dict(row)} for row in matches]


class FakeRequest:
    def __init__(self, args=None):
        self.args = args or {}
        self.path = "/setup"


def _user(user_id):
    return {
        "user_id": user_id,
        "email_id": f"{user_id}@example.test",
        "first_name": "Test",
        "last_name": user_id,
        "status": "ACTIVE",
    }


def _body(response):
    if response.payload in (None, "null"):
        return None
    if isinstance(response.payload, str) and response.payload[:1] in "{[n":
        return json.loads(response.payload)
    return response.payload


def _connection_fields():
    return {
        "zoho_org_id": "800612345",
        "organization_name": "Acme CRM",
        "zoho_user_id": "zuid-1",
        "connected_email": "owner@example.test",
        "connected_name": "Owner",
        "access_token": "zoho-access-secret",
        "refresh_token": "zoho-refresh-secret",
        "token_expires_at": "2026-01-01 00:00:00",
        "scope": "ZohoCRM.modules.READ",
        "status": "connected",
        "last_error": "",
        "accessible_modules": json.dumps([{"api_name": "Leads"}]),
        "modules_synced_at": "2026-01-01 00:00:00",
        "is_active": True,
        "last_selected_at": "2026-01-01 00:00:00",
    }


class ConnectionTenantAccessTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.installation = self.store.add(
            INSTALLATIONS_TABLE,
            {
                "ROWID": "10",
                "installation_key": "marketplace:zoho:8001",
                "source": SOURCE_MARKETPLACE,
                "zoho_org_id": "8001",
                "status": STATUS_ACTIVE,
            },
        )
        self.other_installation = self.store.add(
            INSTALLATIONS_TABLE,
            {
                "ROWID": "11",
                "installation_key": "marketplace:zoho:8002",
                "source": SOURCE_MARKETPLACE,
                "zoho_org_id": "8002",
                "status": STATUS_ACTIVE,
            },
        )
        self.store.add(
            MEMBERS_TABLE,
            {
                "ROWID": "20",
                "installation_id": "10",
                "catalyst_user_id": "owner-1",
                "status": STATUS_ACTIVE,
            },
        )
        self.store.add(
            MEMBERS_TABLE,
            {
                "ROWID": "21",
                "installation_id": "10",
                "catalyst_user_id": "member-1",
                "status": STATUS_ACTIVE,
            },
        )
        self.store.add(
            MEMBERS_TABLE,
            {
                "ROWID": "22",
                "installation_id": "11",
                "catalyst_user_id": "other-member",
                "status": STATUS_ACTIVE,
            },
        )
        self.marketplace_connection = self.store.add(
            ZOHO_CONNECTIONS_TABLE,
            {
                "ROWID": "30",
                "user_id": "owner-1",
                "zoho_org_id": "8001",
                "organization_name": "Acme CRM",
                "connected_name": "Owner",
                "connected_email": "owner@example.test",
                "status": "connected",
                "is_active": True,
                "last_selected_at": "2026-01-02 00:00:00",
                "accessible_modules": json.dumps([{"api_name": "Leads"}]),
                "installation_id": "10",
            },
        )
        self.standalone_connection = self.store.add(
            ZOHO_CONNECTIONS_TABLE,
            {
                "ROWID": "31",
                "user_id": "standalone-1",
                "zoho_org_id": "9001",
                "organization_name": "Standalone Org",
                "connected_name": "Solo",
                "connected_email": "solo@example.test",
                "status": "connected",
                "is_active": True,
                "last_selected_at": "2026-01-01 00:00:00",
                "accessible_modules": "[]",
            },
        )
        self.salesforce_connection = self.store.add(
            SALESFORCE_CONNECTIONS_TABLE,
            {
                "ROWID": "40",
                "user_id": "owner-1",
                "salesforce_org_id": "00Dxx0000001",
                "organization_name": "SF Org",
                "connected_name": "Owner",
                "connected_email": "owner@example.test",
                "instance_url": "https://example.my.salesforce.com",
                "status": "connected",
                "is_active": True,
                "last_selected_at": "2026-01-02 00:00:00",
                "installation_id": "10",
            },
        )
        self.standalone_salesforce = self.store.add(
            SALESFORCE_CONNECTIONS_TABLE,
            {
                "ROWID": "41",
                "user_id": "standalone-1",
                "salesforce_org_id": "00Dxx0000002",
                "organization_name": "SF Solo",
                "connected_name": "Solo",
                "connected_email": "solo@example.test",
                "instance_url": "https://solo.my.salesforce.com",
                "status": "connected",
                "is_active": True,
            },
        )
        self.store.add(
            "scan_jobs",
            {
                "ROWID": "50",
                "scan_id": "scan_abc",
                "connection_row_id": "30",
                "crm_provider": "zoho",
            },
        )

    def _zoho_as(self, user_id):
        sdk = patch("connections.routes.zcatalyst_sdk")
        user = patch("connections.routes.get_current_user", return_value=_user(user_id))
        user_id_patch = patch(
            "connections.routes.get_current_user_id", return_value=user_id
        )
        sdk_cm = sdk.start()
        self.addCleanup(sdk.stop)
        user.start()
        self.addCleanup(user.stop)
        user_id_patch.start()
        self.addCleanup(user_id_patch.stop)
        sdk_cm.initialize.return_value.zcql.return_value = self.store
        return self.store

    def _salesforce_as(self, user_id):
        sdk = patch("salesforce.oauth.zcatalyst_sdk")
        user = patch("salesforce.oauth.get_current_user", return_value=_user(user_id))
        user_id_patch = patch(
            "salesforce.oauth.get_current_user_id", return_value=user_id
        )
        sdk_cm = sdk.start()
        self.addCleanup(sdk.stop)
        user.start()
        self.addCleanup(user.stop)
        user_id_patch.start()
        self.addCleanup(user_id_patch.stop)
        sdk_cm.initialize.return_value.zcql.return_value = self.store
        return self.store

    def test_marketplace_member_can_access_connection(self):
        self._zoho_as("member-1")
        response = get_connection(FakeRequest(), self.store)
        body = _body(response)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["connectionId"], "30")
        self.assertEqual(
            [item["connectionId"] for item in body["availableConnections"]], ["30"]
        )
        activate = activate_connection(FakeRequest(), self.store, "30")
        self.assertEqual(activate.status_code, 200)
        self.assertEqual(_body(activate)["connectionId"], "30")
        self.assertEqual(
            list_accessible_connected_connections(
                self.store, ZOHO_CONNECTIONS_TABLE, "member-1"
            )[0]["ROWID"],
            "30",
        )

        self._salesforce_as("member-1")
        sf_response = get_salesforce_connection(FakeRequest(), self.store)
        self.assertEqual(_body(sf_response)["connectionId"], "40")
        self.assertEqual(
            _select_salesforce_connection(self.store, "member-1")["ROWID"], "40"
        )
        sf_activate = activate_salesforce_connection(FakeRequest(), self.store, "40")
        self.assertEqual(sf_activate.status_code, 200)

    def test_marketplace_non_member_cannot_access_connection(self):
        self._zoho_as("stranger")
        response = get_connection(FakeRequest(), self.store)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(_body(response))
        denied = activate_connection(FakeRequest(), self.store, "30")
        self.assertEqual(denied.status_code, 404)
        self.assertEqual(denied.payload, "Not found")
        self.assertEqual(
            list_accessible_connected_connections(
                self.store, ZOHO_CONNECTIONS_TABLE, "stranger"
            ),
            [],
        )

        self._salesforce_as("stranger")
        self.assertIsNone(_body(get_salesforce_connection(FakeRequest(), self.store)))
        self.assertEqual(
            activate_salesforce_connection(FakeRequest(), self.store, "40").status_code,
            404,
        )
        self.assertIsNone(_select_salesforce_connection(self.store, "stranger"))

    def test_disabled_installation_denies_connection_access(self):
        self.installation["status"] = "disabled"
        self._zoho_as("member-1")
        self.assertIsNone(_body(get_connection(FakeRequest(), self.store)))
        self.assertEqual(
            activate_connection(FakeRequest(), self.store, "30").status_code, 404
        )
        self._zoho_as("owner-1")
        self.assertIsNone(_body(get_connection(FakeRequest(), self.store)))
        self.assertIsNone(_select_salesforce_connection(self.store, "member-1"))
        self.assertIsNone(_select_salesforce_connection(self.store, "owner-1"))

    def test_cross_installation_access_is_denied(self):
        self._zoho_as("other-member")
        self.assertIsNone(_body(get_connection(FakeRequest(), self.store)))
        self.assertEqual(
            activate_connection(FakeRequest(), self.store, "30").status_code, 404
        )
        self.assertIsNone(_select_salesforce_connection(self.store, "other-member"))
        self._salesforce_as("other-member")
        self.assertEqual(
            activate_salesforce_connection(FakeRequest(), self.store, "40").status_code,
            404,
        )

    def test_standalone_owner_can_access_null_installation_connection(self):
        self._zoho_as("standalone-1")
        body = _body(get_connection(FakeRequest(), self.store))
        self.assertEqual(body["connectionId"], "31")
        self.assertNotIn("installation_id", self.standalone_connection)
        activate = activate_connection(FakeRequest(), self.store, "31")
        self.assertEqual(activate.status_code, 200)
        self.assertEqual(_body(activate)["connectionId"], "31")
        self._salesforce_as("standalone-1")
        self.assertEqual(
            _body(get_salesforce_connection(FakeRequest(), self.store))["connectionId"],
            "41",
        )
        self.assertEqual(
            _select_salesforce_connection(self.store, "standalone-1")["ROWID"], "41"
        )

    def test_other_standalone_user_cannot_access_null_installation_connection(self):
        self._zoho_as("standalone-2")
        self.assertIsNone(_body(get_connection(FakeRequest(), self.store)))
        self.assertEqual(
            activate_connection(FakeRequest(), self.store, "31").status_code, 404
        )
        self.assertIsNone(_select_salesforce_connection(self.store, "standalone-2"))
        self._salesforce_as("standalone-2")
        self.assertEqual(
            activate_salesforce_connection(FakeRequest(), self.store, "41").status_code,
            404,
        )

    def test_existing_oauth_behavior_remains_unchanged(self):
        env = {
            "ZOHO_ACCOUNTS_URL": "https://accounts.zoho.in",
            "ZOHO_CLIENT_ID": "client-id",
            "ZOHO_REDIRECT_URI": "https://example.test/api/zoho/callback",
        }
        with patch.dict("os.environ", env, clear=False):
            with patch("connections.routes.get_current_user_id", return_value="user-1"):
                with patch("connections.routes.redirect", side_effect=lambda url: url):
                    location = start_consent(FakeRequest(), self.store)
        self.assertIn("/oauth/v2/auth?", location)
        standalone_state = self.store.rows["oauth_states"][0]
        self.assertEqual(standalone_state["redirect_path"], "/setup")
        self.assertNotEqual(
            standalone_state["redirect_path"], MARKETPLACE_OAUTH_STATE_MARK
        )

        oauth_store = MemoryStore()
        with patch("connections.routes.zcatalyst_sdk") as sdk:
            sdk.initialize.return_value.zcql.return_value = oauth_store
            upsert_connection(oauth_store, "user-1", _connection_fields())
        inserted = oauth_store.rows[ZOHO_CONNECTIONS_TABLE][0]
        self.assertNotIn("installation_id", inserted)
        self.assertEqual(inserted["user_id"], "user-1")
        self.assertEqual(len(oauth_store.rows[INSTALLATIONS_TABLE]), 0)
        self.assertEqual(len(oauth_store.rows[MEMBERS_TABLE]), 0)

        expires = to_catalyst_datetime(datetime.now(timezone.utc) + timedelta(minutes=5))
        oauth_store.table("oauth_states").insert_row(
            {
                "state": "state-1",
                "user_id": "user-1",
                "redirect_path": "/setup",
                "expires_at": expires,
            }
        )
        tokens = {
            "access_token": "zoho-access-secret",
            "refresh_token": "zoho-refresh-secret",
            "expires_in": 3600,
            "api_domain": "https://www.zohoapis.in",
        }
        callback_env = {
            "FRONTEND_SETUP_URL": "https://example.test",
            "ZOHO_API_DOMAIN": "https://www.zohoapis.in",
        }
        with patch.dict("os.environ", callback_env, clear=False):
            with patch("connections.routes.zcatalyst_sdk") as sdk:
                sdk.initialize.return_value.zcql.return_value = oauth_store
                with patch(
                    "connections.routes.get_current_user_id", return_value="user-1"
                ):
                    with patch(
                        "connections.routes.exchange_code_for_tokens",
                        return_value=tokens,
                    ):
                        with patch(
                            "connections.routes.fetch_zoho_profile",
                            return_value={
                                "user_id": "zuid-1",
                                "email": "owner@example.test",
                                "full_name": "Owner",
                            },
                        ):
                            with patch(
                                "connections.routes.fetch_organization_metadata",
                                return_value={
                                    "id": "800612345",
                                    "company_name": "Acme CRM",
                                },
                            ):
                                with patch(
                                    "connections.routes.fetch_accessible_modules",
                                    return_value=[{"api_name": "Leads"}],
                                ):
                                    with patch(
                                        "connections.routes.redirect",
                                        side_effect=lambda url: url,
                                    ):
                                        location = handle_callback(
                                            FakeRequest(
                                                {"state": "state-1", "code": "auth-code"}
                                            ),
                                            oauth_store,
                                        )
        self.assertIn("zoho_connected", location)
        self.assertEqual(oauth_store.rows[INSTALLATIONS_TABLE], [])
        self.assertEqual(oauth_store.rows[MEMBERS_TABLE], [])
        callback_connection = next(
            row
            for row in oauth_store.rows[ZOHO_CONNECTIONS_TABLE]
            if row.get("access_token") == "zoho-access-secret"
        )
        self.assertNotIn("installation_id", callback_connection)
        self.assertEqual(callback_connection["user_id"], "user-1")

    def test_existing_scan_and_report_authorization_uses_dual_read(self):
        scan = {"crm_provider": "zoho", "connection_row_id": "30"}
        self.assertEqual(
            find_owned_scan(self.store, "scan_abc", "member-1")["scan_id"], "scan_abc"
        )
        self.assertEqual(find_scan_connection(self.store, "member-1", scan)["ROWID"], "30")
        self.assertEqual(
            find_owned_scan(self.store, "scan_abc", "owner-1")["scan_id"], "scan_abc"
        )
        self.assertIsNone(find_owned_scan(self.store, "scan_abc", "stranger"))
        self.installation["status"] = "disabled"
        self.assertIsNone(find_owned_scan(self.store, "scan_abc", "member-1"))
        self.assertIsNone(find_owned_scan(self.store, "scan_abc", "owner-1"))
        self.assertIsNone(
            list_accessible_connected_connections(
                self.store, ZOHO_CONNECTIONS_TABLE, "member-1"
            )
            or None
        )


if __name__ == "__main__":
    unittest.main()
