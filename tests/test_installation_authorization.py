import re
import sys
import types
import unittest
from pathlib import Path


FUNCTION_ROOT = (
    Path(__file__).resolve().parents[1]
    / "functions"
    / "ai_data_analytics_function"
)
sys.path.insert(0, str(FUNCTION_ROOT))

if "flask" not in sys.modules:
    flask = types.ModuleType("flask")
    flask.Request = type("Request", (), {})
    flask.make_response = lambda *args, **kwargs: None
    flask.redirect = lambda *args, **kwargs: None
    sys.modules["flask"] = flask

if "zcatalyst_sdk" not in sys.modules:
    zcatalyst_sdk = types.ModuleType("zcatalyst_sdk")
    zcatalyst_sdk.initialize = lambda: None
    sys.modules["zcatalyst_sdk"] = zcatalyst_sdk

from analytics.repository import find_owned_scan
from connections.repository import find_scan_connection
from installations.authorization import (
    find_accessible_zoho_connection,
    resolve_active_installation_for_user,
    resolve_connection_access,
    resolve_connection_through_installation,
)
from installations.repository import (
    INSTALLATIONS_TABLE,
    MEMBERS_TABLE,
    SOURCE_MARKETPLACE,
    STATUS_ACTIVE,
    ZOHO_CONNECTIONS_TABLE,
)


def _quoted(query, column):
    match = re.search(rf"{re.escape(column)} = '((?:[^']|'')*)'", query)
    if not match:
        return None
    return match.group(1).replace("''", "'")


def _rowid_equals(query):
    match = re.search(r"ROWID = (\d+)", query)
    return match.group(1) if match else None


class MemoryStore:
    def __init__(self):
        self.rows = {
            INSTALLATIONS_TABLE: [],
            MEMBERS_TABLE: [],
            ZOHO_CONNECTIONS_TABLE: [],
            "scan_jobs": [],
        }

    def add(self, table, row):
        stored = dict(row)
        self.rows[table].append(stored)
        return stored

    def execute_query(self, query):
        if f"from {INSTALLATIONS_TABLE}" in query:
            matches = list(self.rows[INSTALLATIONS_TABLE])
            row_id = _rowid_equals(query)
            if row_id is not None:
                matches = [row for row in matches if str(row.get("ROWID") or "") == row_id]
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
        if f"from {ZOHO_CONNECTIONS_TABLE}" in query:
            matches = list(self.rows[ZOHO_CONNECTIONS_TABLE])
            row_id = _rowid_equals(query)
            user_id = _quoted(query, "user_id")
            if row_id is not None:
                matches = [row for row in matches if str(row.get("ROWID") or "") == row_id]
            if user_id is not None:
                matches = [
                    row for row in matches if str(row.get("user_id") or "") == user_id
                ]
            if "limit 1" in query:
                matches = matches[:1]
            return [{ZOHO_CONNECTIONS_TABLE: dict(row)} for row in matches]
        if "from scan_jobs" in query:
            matches = list(self.rows["scan_jobs"])
            scan_id = _quoted(query, "scan_id")
            if scan_id is not None:
                matches = [
                    row for row in matches if str(row.get("scan_id") or "") == scan_id
                ]
            if "limit 1" in query:
                matches = matches[:1]
            return [{"scan_jobs": dict(row)} for row in matches]
        raise AssertionError(f"unexpected query: {query}")


class InstallationAuthorizationTests(unittest.TestCase):
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
        self.store.add(
            MEMBERS_TABLE,
            {
                "ROWID": "20",
                "installation_id": "10",
                "catalyst_user_id": "user-1",
                "status": STATUS_ACTIVE,
            },
        )
        self.marketplace_connection = self.store.add(
            ZOHO_CONNECTIONS_TABLE,
            {
                "ROWID": "30",
                "user_id": "owner-1",
                "zoho_org_id": "8001",
                "status": "connected",
                "installation_id": "10",
            },
        )
        self.standalone_connection = self.store.add(
            ZOHO_CONNECTIONS_TABLE,
            {
                "ROWID": "31",
                "user_id": "standalone-1",
                "zoho_org_id": "9001",
                "status": "connected",
            },
        )

    def test_active_member_resolves_installation(self):
        installation = resolve_active_installation_for_user(self.store, "10", "user-1")
        self.assertEqual(installation["ROWID"], "10")

    def test_non_member_cannot_resolve_installation(self):
        self.assertIsNone(
            resolve_active_installation_for_user(self.store, "10", "stranger")
        )

    def test_disabled_installation_is_not_active(self):
        self.installation["status"] = "disabled"
        self.assertIsNone(
            resolve_active_installation_for_user(self.store, "10", "user-1")
        )
        self.assertIsNone(
            resolve_connection_through_installation(
                self.store, self.marketplace_connection, "user-1"
            )
        )

    def test_disabled_membership_is_not_active(self):
        self.store.rows[MEMBERS_TABLE][0]["status"] = "disabled"
        self.assertIsNone(
            resolve_active_installation_for_user(self.store, "10", "user-1")
        )

    def test_marketplace_connection_resolves_through_installation(self):
        resolved = resolve_connection_through_installation(
            self.store, self.marketplace_connection, "user-1"
        )
        self.assertEqual(resolved["ROWID"], "30")
        self.assertEqual(
            find_accessible_zoho_connection(self.store, "30", "user-1")["ROWID"],
            "30",
        )
        # Owner user_id is not required on the tenant helper.
        self.assertIsNone(
            resolve_connection_through_installation(
                self.store, self.marketplace_connection, "owner-1"
            )
        )

    def test_standalone_connection_uses_user_id_ownership(self):
        self.assertEqual(
            resolve_connection_access(
                self.store, self.standalone_connection, "standalone-1"
            )["ROWID"],
            "31",
        )
        self.assertIsNone(
            resolve_connection_access(self.store, self.standalone_connection, "user-1")
        )
        self.assertIsNone(
            resolve_connection_through_installation(
                self.store, self.standalone_connection, "standalone-1"
            )
        )
        scan = {"crm_provider": "zoho", "connection_row_id": "31"}
        self.assertEqual(
            find_scan_connection(self.store, "standalone-1", scan)["ROWID"], "31"
        )
        self.assertIsNone(find_scan_connection(self.store, "user-1", scan))

    def test_one_installation_cannot_access_another_installations_connection(self):
        self.store.add(
            INSTALLATIONS_TABLE,
            {
                "ROWID": "11",
                "source": SOURCE_MARKETPLACE,
                "zoho_org_id": "8002",
                "status": STATUS_ACTIVE,
            },
        )
        self.store.add(
            MEMBERS_TABLE,
            {
                "ROWID": "21",
                "installation_id": "11",
                "catalyst_user_id": "user-2",
                "status": STATUS_ACTIVE,
            },
        )
        other_connection = self.store.add(
            ZOHO_CONNECTIONS_TABLE,
            {
                "ROWID": "32",
                "user_id": "owner-2",
                "installation_id": "11",
                "status": "connected",
            },
        )
        self.assertIsNone(
            resolve_connection_through_installation(
                self.store, other_connection, "user-1"
            )
        )
        self.assertIsNone(find_accessible_zoho_connection(self.store, "32", "user-1"))
        self.assertEqual(
            resolve_connection_through_installation(
                self.store, other_connection, "user-2"
            )["ROWID"],
            "32",
        )

    def test_scan_authorization_uses_dual_read(self):
        self.store.add(
            "scan_jobs",
            {
                "ROWID": "40",
                "scan_id": "scan_abc",
                "connection_row_id": "30",
                "crm_provider": "zoho",
            },
        )
        scan = {"crm_provider": "zoho", "connection_row_id": "30"}
        self.assertEqual(
            find_owned_scan(self.store, "scan_abc", "user-1")["scan_id"], "scan_abc"
        )
        self.assertEqual(find_scan_connection(self.store, "user-1", scan)["ROWID"], "30")
        self.assertIsNone(find_owned_scan(self.store, "scan_abc", "owner-1"))
        self.assertIsNone(find_scan_connection(self.store, "owner-1", scan))
        self.installation["status"] = "disabled"
        self.assertIsNone(find_owned_scan(self.store, "scan_abc", "user-1"))
        self.assertIsNone(
            resolve_connection_access(self.store, self.marketplace_connection, "user-1")
        )
        self.assertIsNone(
            resolve_connection_access(self.store, self.marketplace_connection, "owner-1")
        )


if __name__ == "__main__":
    unittest.main()
