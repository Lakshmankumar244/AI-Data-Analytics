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
from analytics.routes import get_scan_results, get_scan_status
from connections.repository import find_scan_connection
from installations.repository import (
    INSTALLATIONS_TABLE,
    MEMBERS_TABLE,
    SALESFORCE_CONNECTIONS_TABLE,
    SOURCE_MARKETPLACE,
    STATUS_ACTIVE,
    ZOHO_CONNECTIONS_TABLE,
)
from salesforce.scan_create import resolve_active_crm_connection
from scans.delete import delete_scan
from scans.history import list_scans
from scans.routes import create_scan


ZOHO_PAYLOAD = {
    "modules": ["Leads"],
    "depth": "quick",
    "clock": "created",
    "range": {"id": "7d"},
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

    def insert_rows(self, rows):
        return [self.insert_row(row) for row in rows]

    def delete_rows(self, row_ids):
        keep = [
            row
            for row in self.store.rows.get(self.name, [])
            if int(row["ROWID"]) not in {int(item) for item in row_ids}
        ]
        self.store.rows[self.name] = keep


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
            "analytics_results": [],
            "bulk_read_jobs": [],
            "processing_batches": [],
            "pipeline_tasks": [],
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
        module_row_id = _unquoted(query, "scan_module_row_id")
        if module_row_id is not None:
            matches = [
                row
                for row in matches
                if str(row.get("scan_module_row_id") or "") == module_row_id
            ]
        bulk_job_row_id = _unquoted(query, "bulk_job_row_id")
        if bulk_job_row_id is not None:
            matches = [
                row
                for row in matches
                if str(row.get("bulk_job_row_id") or "") == bulk_job_row_id
            ]
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


class ExistingScanTenantAccessTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.installation = self.store.add(
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
                "accessible_modules": json.dumps([{"apiName": "Leads"}]),
                "installation_id": "10",
            },
        )
        self.store.add(
            ZOHO_CONNECTIONS_TABLE,
            {
                "ROWID": "32",
                "user_id": "other-owner",
                "zoho_org_id": "8002",
                "organization_name": "Other CRM",
                "status": "connected",
                "is_active": True,
                "accessible_modules": json.dumps([{"apiName": "Leads"}]),
                "installation_id": "11",
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
        self.marketplace_scan = self.store.add(
            "scan_jobs",
            {
                "ROWID": "50",
                "scan_id": "scan_abc",
                "connection_row_id": "30",
                "crm_provider": "zoho",
                "status": "CREATED",
                "clock_field": "Created_Time",
                "depth_policy": "quick",
                "CREATEDTIME": "2026-01-02 00:00:00",
            },
        )
        self.other_scan = self.store.add(
            "scan_jobs",
            {
                "ROWID": "51",
                "scan_id": "scan_other",
                "connection_row_id": "32",
                "crm_provider": "zoho",
                "status": "CREATED",
                "CREATEDTIME": "2026-01-02 01:00:00",
            },
        )
        self.standalone_scan = self.store.add(
            "scan_jobs",
            {
                "ROWID": "52",
                "scan_id": "scan_solo",
                "connection_row_id": "31",
                "crm_provider": "zoho",
                "status": "CREATED",
                "CREATEDTIME": "2026-01-03 00:00:00",
            },
        )

    def _as_user(self, module_path, user_id):
        sdk = patch(f"{module_path}.zcatalyst_sdk")
        user = patch(f"{module_path}.get_current_user_id", return_value=user_id)
        sdk_cm = sdk.start()
        self.addCleanup(sdk.stop)
        user.start()
        self.addCleanup(user.stop)
        sdk_cm.initialize.return_value.zcql.return_value = self.store
        return self.store

    def _history(self, user_id):
        self._as_user("scans.history", user_id)
        return list_scans(FakeRequest(), self.store)

    def _status(self, user_id, scan_id="scan_abc"):
        self._as_user("analytics.routes", user_id)
        return get_scan_status(FakeRequest(), self.store, scan_id)

    def _results(self, user_id, scan_id="scan_abc"):
        self._as_user("analytics.routes", user_id)
        return get_scan_results(FakeRequest(), self.store, scan_id)

    def test_marketplace_member_can_view_scan(self):
        self.assertEqual(
            find_owned_scan(self.store, "scan_abc", "member-1")["scan_id"], "scan_abc"
        )
        self.assertEqual(
            find_scan_connection(
                self.store, "member-1", {"crm_provider": "zoho", "connection_row_id": "30"}
            )["ROWID"],
            "30",
        )
        response = self._status("member-1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(_body(response)["scanId"], "scan_abc")

    def test_marketplace_member_can_view_scan_report(self):
        response = self._results("member-1")
        self.assertEqual(response.status_code, 200)
        body = _body(response)
        self.assertEqual(body["scanId"], "scan_abc")
        self.assertIn("modules", body)

    def test_marketplace_non_member_cannot_view_scan(self):
        self.assertIsNone(find_owned_scan(self.store, "scan_abc", "stranger"))
        self.assertIsNone(
            find_scan_connection(
                self.store, "stranger", {"crm_provider": "zoho", "connection_row_id": "30"}
            )
        )
        self.assertEqual(self._status("stranger").status_code, 404)
        self.assertEqual(_body(self._status("stranger"))["error"]["code"], "SCAN_NOT_FOUND")
        self.assertEqual(self._results("stranger").status_code, 404)
        self._as_user("scans.delete", "stranger")
        denied = delete_scan(
            FakeRequest({"confirmScanId": "scan_abc"}), self.store, "scan_abc"
        )
        self.assertEqual(denied.status_code, 404)

    def test_disabled_installation_denies_scan_access(self):
        self.installation["status"] = "disabled"
        for user_id in ("member-1", "owner-1"):
            self.assertIsNone(find_owned_scan(self.store, "scan_abc", user_id))
            self.assertEqual(self._status(user_id).status_code, 404)
            ids = [item["scanId"] for item in _body(self._history(user_id))["scans"]]
            self.assertNotIn("scan_abc", ids)

    def test_cross_installation_scan_access_is_denied(self):
        self.assertIsNone(find_owned_scan(self.store, "scan_abc", "other-member"))
        self.assertEqual(self._status("other-member").status_code, 404)
        ids = [item["scanId"] for item in _body(self._history("other-member"))["scans"]]
        self.assertEqual(ids, ["scan_other"])
        self.assertNotIn("scan_abc", ids)

    def test_standalone_owner_can_view_scan(self):
        self.assertEqual(
            find_owned_scan(self.store, "scan_solo", "standalone-1")["scan_id"],
            "scan_solo",
        )
        response = self._status("standalone-1", "scan_solo")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(_body(response)["scanId"], "scan_solo")
        ids = [item["scanId"] for item in _body(self._history("standalone-1"))["scans"]]
        self.assertEqual(ids, ["scan_solo"])

    def test_other_standalone_user_cannot_view_scan(self):
        self.assertIsNone(find_owned_scan(self.store, "scan_solo", "standalone-2"))
        self.assertEqual(self._status("standalone-2", "scan_solo").status_code, 404)
        self.assertEqual(_body(self._history("standalone-2"))["scans"], [])

    def test_marketplace_member_sees_installation_scan_history(self):
        ids = [item["scanId"] for item in _body(self._history("member-1"))["scans"]]
        self.assertEqual(ids, ["scan_abc"])
        self.assertNotIn("scan_other", ids)
        self.assertNotIn("scan_solo", ids)
        connection = _body(self._history("member-1"))["scans"][0]["connection"]
        self.assertEqual(connection["connectionId"], "30")
        self.assertEqual(connection["organizationId"], "8001")

    def test_existing_scan_creation_behavior_remains_unchanged(self):
        provider, row = resolve_active_crm_connection(self.store, "member-1")
        self.assertEqual(provider, "zoho")
        self.assertEqual(row["ROWID"], "30")
        sdk = patch("scans.routes.zcatalyst_sdk")
        user = patch("scans.routes.get_current_user_id", return_value="member-1")
        enqueue = patch(
            "scans.routes.enqueue_orchestrate_scan",
            return_value={"ok": True, "submitted": True},
        )
        sdk_cm = sdk.start()
        self.addCleanup(sdk.stop)
        user.start()
        self.addCleanup(user.stop)
        enqueue.start()
        self.addCleanup(enqueue.stop)
        sdk_cm.initialize.return_value.zcql.return_value = self.store
        response = create_scan(FakeRequest(ZOHO_PAYLOAD), self.store)
        self.assertEqual(response.status_code, 201)
        created_id = _body(response)["scanId"]
        self.assertEqual(
            find_owned_scan(self.store, created_id, "member-1")["scan_id"], created_id
        )

    def test_scan_execution_worker_authorization_remains_user_id(self):
        worker = (ZOHO_WORKER / "connections" / "repository.py").read_text(
            encoding="utf-8"
        )
        http = (FUNCTION_ROOT / "connections" / "repository.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("find_accessible_connected_connection_by_id", http)
        self.assertNotIn("find_accessible_connected_connection_by_id", worker)
        self.assertIn("and user_id = '{_escape(user_id)}'", worker)
        self.assertIn("find_persisted_scan_connection", worker)
        self.assertIn("find_persisted_scan_connection", http)


if __name__ == "__main__":
    unittest.main()
