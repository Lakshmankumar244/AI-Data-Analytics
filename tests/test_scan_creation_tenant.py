import json
import re
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
FUNCTION_ROOT = ROOT / "functions" / "ai_data_analytics_function"
ZOHO_WORKER = ROOT / "functions" / "ai_data_analytics_worker"
SF_WORKER = ROOT / "functions" / "ai_data_analytics_salesforce_worker"
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
from connections.repository import find_active_connection, find_scan_connection
from installations.authorization import find_accessible_active_connection
from installations.repository import (
    INSTALLATIONS_TABLE,
    MEMBERS_TABLE,
    SALESFORCE_CONNECTIONS_TABLE,
    SOURCE_MARKETPLACE,
    STATUS_ACTIVE,
    ZOHO_CONNECTIONS_TABLE,
)
from salesforce.oauth import find_active_salesforce_connection
from salesforce.scan_create import resolve_active_crm_connection
from scans.routes import create_scan


ZOHO_PAYLOAD = {
    "modules": ["Leads"],
    "depth": "quick",
    "clock": "created",
    "range": {"id": "7d"},
}
SF_PAYLOAD = {
    "modules": ["Account"],
    "depth": "quick",
    "clock": "created",
    "range": {"id": "7d"},
}
ACCOUNT_DESCRIBE = {
    "name": "Account",
    "label": "Account",
    "custom": False,
    "queryable": True,
    "fields": [
        {
            "name": "Id",
            "label": "Account ID",
            "type": "id",
            "nillable": False,
            "unique": True,
            "createable": False,
            "updateable": False,
            "calculated": False,
            "custom": False,
            "filterable": True,
            "restrictedPicklist": False,
            "referenceTo": [],
            "length": 18,
            "nameField": False,
        },
        {
            "name": "CreatedDate",
            "label": "Created Date",
            "type": "datetime",
            "nillable": False,
            "createable": False,
            "updateable": False,
            "calculated": False,
            "custom": False,
            "filterable": True,
            "restrictedPicklist": False,
            "referenceTo": [],
            "length": 0,
            "nameField": False,
        },
        {
            "name": "LastModifiedDate",
            "label": "Last Modified Date",
            "type": "datetime",
            "nillable": False,
            "createable": False,
            "updateable": False,
            "calculated": False,
            "custom": False,
            "filterable": True,
            "restrictedPicklist": False,
            "referenceTo": [],
            "length": 0,
            "nameField": False,
        },
        {
            "name": "Name",
            "label": "Account Name",
            "type": "string",
            "nillable": False,
            "unique": False,
            "createable": True,
            "updateable": True,
            "calculated": False,
            "custom": False,
            "filterable": True,
            "restrictedPicklist": False,
            "referenceTo": [],
            "length": 255,
            "nameField": True,
        },
    ],
}


def _quoted(query, column):
    match = re.search(
        rf"(?<![A-Za-z0-9_]){re.escape(column)} = '((?:[^']|'')*)'", query
    )
    if not match:
        return None
    return match.group(1).replace("''", "'")


def _unquoted(query, column):
    match = re.search(rf"(?<![A-Za-z0-9_]){re.escape(column)} = (\d+)", query)
    return match.group(1) if match else None


def _rowid_equals(query):
    return _unquoted(query, "ROWID")


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

    def insert_rows(self, rows):
        return [self.insert_row(row) for row in rows]

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
            "scan_jobs": [],
            "scan_module_runs": [],
        }

    def table(self, name):
        self.rows.setdefault(name, [])
        return MemoryTable(self, name)

    def add(self, table, row):
        stored = dict(row)
        self.rows.setdefault(table, []).append(stored)
        return stored

    def execute_query(self, query):
        table = None
        for name in (
            INSTALLATIONS_TABLE,
            MEMBERS_TABLE,
            ZOHO_CONNECTIONS_TABLE,
            SALESFORCE_CONNECTIONS_TABLE,
            "scan_jobs",
            "scan_module_runs",
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
        connection_row_id = _unquoted(query, "connection_row_id")
        if connection_row_id is not None:
            matches = [
                row
                for row in matches
                if str(row.get("connection_row_id") or "") == connection_row_id
            ]
        scan_row_id = _unquoted(query, "scan_row_id")
        if scan_row_id is not None:
            matches = [
                row
                for row in matches
                if str(row.get("scan_row_id") or "") == scan_row_id
            ]
        if "status = 'connected'" in query:
            matches = [
                row for row in matches if str(row.get("status") or "") == "connected"
            ]
        if "limit 1" in query:
            matches = matches[:1]
        elif "limit 20" in query:
            matches = matches[:20]
        return [{table: dict(row)} for row in matches]


class FakeRequest:
    def __init__(self, payload=None):
        self._payload = payload
        self.args = {}
        self.path = "/api/scans"

    def get_json(self, silent=True):
        del silent
        return self._payload


def _body(response):
    if hasattr(response, "get_json"):
        try:
            return response.get_json()
        except Exception:
            pass
    if isinstance(response.payload, str):
        return json.loads(response.payload)
    return response.payload


class ScanCreationTenantTests(unittest.TestCase):
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
        for row_id, installation_id, user_id in (
            ("20", "10", "owner-1"),
            ("21", "10", "member-1"),
            ("22", "11", "other-member"),
        ):
            self.store.add(
                MEMBERS_TABLE,
                {
                    "ROWID": row_id,
                    "installation_id": installation_id,
                    "catalyst_user_id": user_id,
                    "status": STATUS_ACTIVE,
                },
            )
        self.marketplace_zoho = self.store.add(
            ZOHO_CONNECTIONS_TABLE,
            {
                "ROWID": "30",
                "user_id": "owner-1",
                "zoho_org_id": "8001",
                "status": "connected",
                "is_active": True,
                "last_selected_at": "2026-01-02 00:00:00",
                "accessible_modules": json.dumps([{"apiName": "Leads"}]),
                "installation_id": "10",
            },
        )
        self.other_marketplace_zoho = self.store.add(
            ZOHO_CONNECTIONS_TABLE,
            {
                "ROWID": "32",
                "user_id": "other-owner",
                "zoho_org_id": "8002",
                "status": "connected",
                "is_active": True,
                "last_selected_at": "2026-01-02 00:00:00",
                "accessible_modules": json.dumps([{"apiName": "Leads"}]),
                "installation_id": "11",
            },
        )
        self.standalone_zoho = self.store.add(
            ZOHO_CONNECTIONS_TABLE,
            {
                "ROWID": "31",
                "user_id": "standalone-1",
                "zoho_org_id": "9001",
                "status": "connected",
                "is_active": True,
                "last_selected_at": "2026-01-03 00:00:00",
                "accessible_modules": json.dumps([{"apiName": "Leads"}]),
            },
        )
        self.marketplace_salesforce = self.store.add(
            SALESFORCE_CONNECTIONS_TABLE,
            {
                "ROWID": "40",
                "user_id": "owner-1",
                "salesforce_org_id": "00Dxx0000001",
                "status": "connected",
                "is_active": False,
                "last_selected_at": "2026-01-01 00:00:00",
                "installation_id": "10",
            },
        )
        self.standalone_salesforce = self.store.add(
            SALESFORCE_CONNECTIONS_TABLE,
            {
                "ROWID": "41",
                "user_id": "standalone-1",
                "salesforce_org_id": "00Dxx0000002",
                "status": "connected",
                "is_active": False,
                "last_selected_at": "2026-01-01 00:00:00",
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

    def _create_as(self, user_id, payload, salesforce=False):
        sdk = patch("scans.routes.zcatalyst_sdk")
        user = patch("scans.routes.get_current_user_id", return_value=user_id)
        enqueue = patch(
            "scans.routes.enqueue_orchestrate_scan",
            return_value={"ok": True, "submitted": True, "alreadyActive": False},
        )
        sdk_cm = sdk.start()
        self.addCleanup(sdk.stop)
        user.start()
        self.addCleanup(user.stop)
        enqueue.start()
        self.addCleanup(enqueue.stop)
        sdk_cm.initialize.return_value.zcql.return_value = self.store
        extra = []
        if salesforce:
            extra = [
                patch(
                    "salesforce.client.get_salesforce_access_token",
                    return_value=(
                        "stored-access-token",
                        "https://example.my.salesforce.com",
                    ),
                ),
                patch(
                    "salesforce.client.fetch_salesforce_organization",
                    return_value={
                        "id": "00Dxx0000001",
                        "name": "Acme",
                        "timeZone": "America/Los_Angeles",
                    },
                ),
                patch("salesforce.client.persist_salesforce_organization_name"),
                patch(
                    "salesforce.client.fetch_accessible_sobjects",
                    return_value=[{"apiName": "Account", "label": "Account"}],
                ),
                patch(
                    "salesforce.describe.fetch_sobject_describe",
                    return_value=ACCOUNT_DESCRIBE,
                ),
                patch(
                    "salesforce.user_directory.sync_salesforce_owner_directory",
                    return_value={
                        "refreshed": True,
                        "apiCalls": 1,
                        "counts": {"user": 1, "queue": 0, "group": 0},
                        "warning": None,
                    },
                ),
                patch(
                    "salesforce.scan_create._enqueue_salesforce_worker",
                    return_value={
                        "ok": True,
                        "submitted": True,
                        "alreadyActive": False,
                        "task": {
                            "task_id": "task_sf_test",
                            "status": "QUEUED",
                            "task_type": "ORCHESTRATE_SALESFORCE_SCAN",
                        },
                    },
                ),
            ]
            for item in extra:
                item.start()
                self.addCleanup(item.stop)
        return create_scan(FakeRequest(payload), self.store)

    def test_standalone_owner_can_create_zoho_scan(self):
        response = self._create_as("standalone-1", ZOHO_PAYLOAD)
        body = _body(response)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(body["status"], "CREATED")
        self.assertFalse(body["reused"])
        self.assertEqual(body["modules"], ["Leads"])
        created = next(
            row
            for row in self.store.rows["scan_jobs"]
            if row.get("scan_id") == body["scanId"]
        )
        self.assertEqual(str(created["connection_row_id"]), "31")
        self.assertNotIn("crm_provider", created)
        provider, row = resolve_active_crm_connection(self.store, "standalone-1")
        self.assertEqual(provider, "zoho")
        self.assertEqual(row["ROWID"], "31")

    def test_standalone_owner_can_create_salesforce_scan(self):
        self.standalone_zoho["is_active"] = False
        self.standalone_salesforce["is_active"] = True
        response = self._create_as("standalone-1", SF_PAYLOAD, salesforce=True)
        body = _body(response)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(body["crmProvider"], "salesforce")
        created = next(
            row
            for row in self.store.rows["scan_jobs"]
            if row.get("scan_id") == body["scanId"]
        )
        self.assertEqual(str(created["connection_row_id"]), "41")
        self.assertEqual(created["crm_provider"], "salesforce")
        provider, row = resolve_active_crm_connection(self.store, "standalone-1")
        self.assertEqual(provider, "salesforce")
        self.assertEqual(row["ROWID"], "41")

    def test_marketplace_member_can_create_scan(self):
        response = self._create_as("member-1", ZOHO_PAYLOAD)
        body = _body(response)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(body["status"], "CREATED")
        created = next(
            row
            for row in self.store.rows["scan_jobs"]
            if row.get("scan_id") == body["scanId"]
        )
        self.assertEqual(str(created["connection_row_id"]), "30")
        provider, row = resolve_active_crm_connection(self.store, "member-1")
        self.assertEqual(provider, "zoho")
        self.assertEqual(row["ROWID"], "30")
        self.assertEqual(row["user_id"], "owner-1")

    def test_marketplace_non_member_cannot_create_scan(self):
        response = self._create_as("stranger", ZOHO_PAYLOAD)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(_body(response)["error"]["code"], "ZOHO_CONNECTION_REQUIRED")
        self.assertEqual(
            [row for row in self.store.rows["scan_jobs"] if row["ROWID"] != "50"],
            [],
        )
        self.assertIsNone(resolve_active_crm_connection(self.store, "stranger")[1])

    def test_disabled_marketplace_installation_cannot_create_scan(self):
        self.installation["status"] = "disabled"
        for user_id in ("member-1", "owner-1"):
            response = self._create_as(user_id, ZOHO_PAYLOAD)
            self.assertEqual(response.status_code, 409)
            self.assertEqual(
                _body(response)["error"]["code"], "ZOHO_CONNECTION_REQUIRED"
            )
            self.assertIsNone(resolve_active_crm_connection(self.store, user_id)[1])

    def test_marketplace_member_cannot_create_scan_against_another_installation(self):
        provider, row = resolve_active_crm_connection(self.store, "other-member")
        self.assertEqual(provider, "zoho")
        self.assertEqual(row["ROWID"], "32")
        self.assertNotEqual(row["ROWID"], "30")
        response = self._create_as("other-member", ZOHO_PAYLOAD)
        body = _body(response)
        self.assertEqual(response.status_code, 201)
        created = next(
            item
            for item in self.store.rows["scan_jobs"]
            if item.get("scan_id") == body["scanId"]
        )
        self.assertEqual(str(created["connection_row_id"]), "32")
        self.assertNotEqual(str(created["connection_row_id"]), "30")

    def test_existing_standalone_behavior_remains_unchanged(self):
        self.assertNotIn("installation_id", self.standalone_zoho)
        self.assertEqual(
            find_active_connection(self.store, "standalone-1")["ROWID"], "31"
        )
        self.assertIsNone(find_active_connection(self.store, "member-1"))
        response = self._create_as("standalone-2", ZOHO_PAYLOAD)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(_body(response)["error"]["code"], "ZOHO_CONNECTION_REQUIRED")

    def test_active_marketplace_connection_resolution_uses_membership(self):
        self.assertEqual(
            find_accessible_active_connection(
                self.store, ZOHO_CONNECTIONS_TABLE, "member-1"
            )["ROWID"],
            "30",
        )
        self.assertIsNone(
            find_accessible_active_connection(
                self.store, ZOHO_CONNECTIONS_TABLE, "stranger"
            )
        )
        self.assertIsNone(find_active_connection(self.store, "member-1"))
        self.assertEqual(find_active_connection(self.store, "owner-1")["ROWID"], "30")
        provider, row = resolve_active_crm_connection(self.store, "member-1")
        self.assertEqual(provider, "zoho")
        self.assertEqual(row["ROWID"], "30")
        self.marketplace_zoho["is_active"] = False
        self.marketplace_salesforce["is_active"] = True
        provider, row = resolve_active_crm_connection(self.store, "member-1")
        self.assertEqual(provider, "salesforce")
        self.assertEqual(row["ROWID"], "40")
        self.assertIsNone(find_active_salesforce_connection(self.store, "member-1"))
        self.assertEqual(
            find_active_salesforce_connection(self.store, "owner-1")["ROWID"], "40"
        )

    def test_scan_execution_and_worker_helpers_remain_user_id(self):
        worker_repo = (
            ZOHO_WORKER / "connections" / "repository.py"
        ).read_text(encoding="utf-8")
        http_repo = (
            FUNCTION_ROOT / "connections" / "repository.py"
        ).read_text(encoding="utf-8")
        oauth = (FUNCTION_ROOT / "salesforce" / "oauth.py").read_text(encoding="utf-8")
        scan_create = (
            FUNCTION_ROOT / "salesforce" / "scan_create.py"
        ).read_text(encoding="utf-8")
        worker_describe = (
            SF_WORKER / "salesforce" / "describe.py"
        ).read_text(encoding="utf-8")
        self.assertIn("find_accessible_active_connection", scan_create)
        self.assertNotIn("find_active_connection(", scan_create)
        self.assertNotIn("find_active_salesforce_connection(", scan_create)
        self.assertIn("user_id = '{_escape(user_id)}' and status = 'connected'", http_repo)
        self.assertNotIn("find_accessible_active_connection", http_repo)
        self.assertIn(
            "user_id = '{_escape(user_id)}' and status = 'connected'", worker_repo
        )
        self.assertNotIn("find_accessible_active_connection", worker_repo)
        self.assertIn(
            "user_id = '{_escape_zcql(user_id)}' and status = 'connected'", oauth
        )
        self.assertIn("find_active_salesforce_connection", worker_describe)
        self.assertNotIn("find_accessible_active_connection", worker_describe)

    def test_existing_scan_and_report_authorization_uses_dual_read(self):
        scan = {"crm_provider": "zoho", "connection_row_id": "30"}
        self.assertEqual(
            find_owned_scan(self.store, "scan_abc", "member-1")["scan_id"], "scan_abc"
        )
        self.assertEqual(find_scan_connection(self.store, "member-1", scan)["ROWID"], "30")
        self.assertEqual(
            find_owned_scan(self.store, "scan_abc", "owner-1")["scan_id"], "scan_abc"
        )
        created = self._create_as("member-1", ZOHO_PAYLOAD)
        scan_id = _body(created)["scanId"]
        self.assertEqual(find_owned_scan(self.store, scan_id, "member-1")["scan_id"], scan_id)
        self.assertEqual(find_owned_scan(self.store, scan_id, "owner-1")["scan_id"], scan_id)
        self.assertIsNone(find_owned_scan(self.store, scan_id, "stranger"))


if __name__ == "__main__":
    unittest.main()
