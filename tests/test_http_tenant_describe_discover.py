import json
import re
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
FUNCTION_ROOT = ROOT / "functions" / "ai_data_analytics_function"
SF_WORKER = ROOT / "functions" / "ai_data_analytics_salesforce_worker"
ZOHO_WORKER = ROOT / "functions" / "ai_data_analytics_worker"
SHARED = ROOT / "functions" / "_shared"
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

from installations.repository import (
    INSTALLATIONS_TABLE,
    MEMBERS_TABLE,
    SALESFORCE_CONNECTIONS_TABLE,
    SOURCE_MARKETPLACE,
    STATUS_ACTIVE,
    ZOHO_CONNECTIONS_TABLE,
)
from salesforce.describe_route import get_salesforce_object_describe
from scans.discover import discover_scan


DESCRIBED = {
    "object": {
        "apiName": "Account",
        "label": "Account",
        "custom": False,
        "queryable": True,
    },
    "allowlist": ["Id"],
    "fields": [{"apiName": "Id"}],
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


class MemoryStore:
    def __init__(self):
        self.next_id = 100
        self.rows = {
            INSTALLATIONS_TABLE: [],
            MEMBERS_TABLE: [],
            ZOHO_CONNECTIONS_TABLE: [],
            SALESFORCE_CONNECTIONS_TABLE: [],
            "scan_jobs": [],
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
        for name in self.rows:
            if f"from {name}" in query:
                table = name
                break
        if table is None:
            raise AssertionError(f"unexpected query: {query}")
        matches = list(self.rows[table])
        row_id = _unquoted(query, "ROWID")
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
        if "status = 'connected'" in query:
            matches = [
                row for row in matches if str(row.get("status") or "") == "connected"
            ]
        if "limit 1" in query:
            matches = matches[:1]
        return [{table: dict(row)} for row in matches]


class FakeRequest:
    def __init__(self, payload=None):
        self._payload = payload
        self.args = {}
        self.path = "/api"


def _body(response):
    if hasattr(response, "get_json"):
        try:
            return response.get_json()
        except Exception:
            pass
    if isinstance(response.payload, str):
        return json.loads(response.payload)
    return response.payload


class HttpTenantDescribeDiscoverTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.store.add(
            INSTALLATIONS_TABLE,
            {
                "ROWID": "10",
                "source": SOURCE_MARKETPLACE,
                "zoho_org_id": "8001",
                "status": STATUS_ACTIVE,
            },
        )
        self.store.add(
            INSTALLATIONS_TABLE,
            {
                "ROWID": "11",
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
        self.store.add(
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
        self.store.add(
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
            ZOHO_CONNECTIONS_TABLE,
            {
                "ROWID": "31",
                "user_id": "standalone-1",
                "zoho_org_id": "9001",
                "organization_name": "Solo Org",
                "status": "connected",
                "is_active": True,
                "accessible_modules": json.dumps([{"apiName": "Leads"}]),
            },
        )
        self.store.add(
            "scan_jobs",
            {
                "ROWID": "60",
                "scan_id": "scan_sf",
                "connection_row_id": "40",
                "crm_provider": "salesforce",
                "status": "CREATED",
            },
        )
        self.store.add(
            "scan_jobs",
            {
                "ROWID": "61",
                "scan_id": "scan_sf_solo",
                "connection_row_id": "41",
                "crm_provider": "salesforce",
                "status": "CREATED",
            },
        )
        self.store.add(
            "scan_jobs",
            {
                "ROWID": "52",
                "scan_id": "scan_solo",
                "connection_row_id": "31",
                "crm_provider": "zoho",
                "status": "PLANNED",
            },
        )

    def _describe(self, user_id):
        sdk = patch("salesforce.describe_route.zcatalyst_sdk")
        user = patch(
            "salesforce.describe_route.get_current_user_id", return_value=user_id
        )
        token = patch(
            "salesforce.describe_route.get_salesforce_access_token",
            return_value=("sf-token", "https://example.my.salesforce.com"),
        )
        fetch = patch(
            "salesforce.describe_route.fetch_sobject_describe",
            return_value={"name": "Account", "fields": []},
        )
        fields = patch(
            "salesforce.describe_route.describe_salesforce_fields",
            return_value=DESCRIBED,
        )
        sdk_cm = sdk.start()
        self.addCleanup(sdk.stop)
        user.start()
        self.addCleanup(user.stop)
        token.start()
        self.addCleanup(token.stop)
        fetch.start()
        self.addCleanup(fetch.stop)
        fields.start()
        self.addCleanup(fields.stop)
        sdk_cm.initialize.return_value.zcql.return_value = self.store
        return get_salesforce_object_describe(FakeRequest(), self.store, "Account")

    def _discover(self, user_id, scan_id):
        sdk = patch("scans.discover.zcatalyst_sdk")
        user = patch("scans.discover.get_current_user_id", return_value=user_id)
        action_user = patch(
            "connections.access.get_current_user_id", return_value=user_id
        )
        sdk_cm = sdk.start()
        self.addCleanup(sdk.stop)
        user.start()
        self.addCleanup(user.stop)
        action_user.start()
        self.addCleanup(action_user.stop)
        sdk_cm.initialize.return_value.zcql.return_value = self.store
        return discover_scan(FakeRequest(), self.store, scan_id)

    def test_marketplace_member_can_use_salesforce_describe(self):
        response = self._describe("member-1")
        body = _body(response)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["connectionId"], "40")
        self.assertEqual(body["object"]["apiName"], "Account")
        self.assertEqual(body["allowlist"], ["Id"])

    def test_non_member_cannot_use_salesforce_describe(self):
        for user_id in ("stranger", "other-member"):
            response = self._describe(user_id)
            body = _body(response)
            self.assertEqual(response.status_code, 409, user_id)
            self.assertEqual(body["error"]["code"], "SALESFORCE_CONNECTION_REQUIRED")
            self.assertNotIn("connectionId", body)

    def test_standalone_salesforce_owner_can_use_describe(self):
        response = self._describe("standalone-1")
        body = _body(response)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["connectionId"], "41")
        self.assertEqual(body["object"]["apiName"], "Account")

    def test_marketplace_member_reaches_salesforce_discover_behavior(self):
        response = self._discover("member-1", "scan_sf")
        body = _body(response)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(body["error"]["code"], "SALESFORCE_EXTRACTION_NOT_IMPLEMENTED")
        self.assertEqual(
            body["error"]["message"],
            "Salesforce scan extraction is not implemented yet",
        )

    def test_non_member_cannot_learn_salesforce_scan_exists_through_discover(self):
        missing = self._discover("stranger", "scan_missing")
        denied = self._discover("stranger", "scan_sf")
        cross = self._discover("other-member", "scan_sf")
        for response in (missing, denied, cross):
            body = _body(response)
            self.assertEqual(response.status_code, 404)
            self.assertEqual(body["error"]["code"], "SCAN_NOT_FOUND")
            payload = json.dumps(body).lower()
            self.assertNotIn("salesforce", payload)
            self.assertNotIn("extraction_not_implemented", payload)

    def test_standalone_discover_behavior_remains_unchanged(self):
        salesforce_owner = self._discover("standalone-1", "scan_sf_solo")
        self.assertEqual(salesforce_owner.status_code, 409)
        self.assertEqual(
            _body(salesforce_owner)["error"]["code"],
            "SALESFORCE_EXTRACTION_NOT_IMPLEMENTED",
        )
        salesforce_other = self._discover("standalone-2", "scan_sf_solo")
        self.assertEqual(salesforce_other.status_code, 404)
        self.assertEqual(_body(salesforce_other)["error"]["code"], "SCAN_NOT_FOUND")
        zoho_owner = self._discover("standalone-1", "scan_solo")
        self.assertEqual(zoho_owner.status_code, 200)
        self.assertEqual(_body(zoho_owner)["scanId"], "scan_solo")
        self.assertTrue(_body(zoho_owner)["alreadyDiscovered"])
        zoho_other = self._discover("standalone-2", "scan_solo")
        self.assertEqual(zoho_other.status_code, 409)
        self.assertEqual(
            _body(zoho_other)["error"]["code"], "ZOHO_CONNECTION_REQUIRED"
        )


class SalesforceHttpWorkerSeparationTests(unittest.TestCase):
    def test_salesforce_worker_describe_and_discover_remain_unchanged(self):
        shared = (SHARED / "salesforce" / "describe.py").read_bytes()
        http_copy = (FUNCTION_ROOT / "salesforce" / "describe.py").read_bytes()
        worker_copy = (SF_WORKER / "salesforce" / "describe.py").read_bytes()
        self.assertEqual(shared, http_copy)
        self.assertEqual(shared, worker_copy)

        worker_describe = worker_copy.decode("utf-8")
        self.assertIn("find_active_salesforce_connection", worker_describe)
        self.assertIn("find_connected_salesforce_connection", worker_describe)
        self.assertNotIn("find_accessible_connected_connection", worker_describe)
        self.assertNotIn("installations.authorization", worker_describe)

        http_route = (FUNCTION_ROOT / "salesforce" / "describe_route.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("find_accessible_connected_connection", http_route)
        self.assertIn("describe_salesforce_fields", http_route)
        self.assertNotIn("find_active_salesforce_connection", http_route)
        self.assertFalse((SHARED / "salesforce" / "describe_route.py").exists())
        self.assertFalse((SF_WORKER / "salesforce" / "describe_route.py").exists())
        self.assertFalse((ZOHO_WORKER / "salesforce" / "describe_route.py").exists())

        router = (FUNCTION_ROOT / "api" / "router.py").read_text(encoding="utf-8")
        self.assertIn("from salesforce.describe_route import get_salesforce_object_describe", router)
        self.assertNotIn("from salesforce.describe import get_salesforce_object_describe", router)

        worker_discover = (ZOHO_WORKER / "scans" / "discover.py").read_text(
            encoding="utf-8"
        )
        http_discover = (FUNCTION_ROOT / "scans" / "discover.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("find_owned_scan", worker_discover)
        self.assertNotIn("SALESFORCE_EXTRACTION_NOT_IMPLEMENTED", worker_discover)
        self.assertIn("find_owned_scan", http_discover)
        owned_at = http_discover.index("find_owned_scan")
        denied_at = http_discover.index("SALESFORCE_EXTRACTION_NOT_IMPLEMENTED")
        self.assertLess(owned_at, denied_at)


if __name__ == "__main__":
    unittest.main()
