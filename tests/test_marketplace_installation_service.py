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

    class FakeFlaskResponse:
        def __init__(self, payload, status=200, headers=None):
            self.payload = payload
            self.status_code = status
            self.headers = headers or {}

    flask.make_response = lambda payload, status=200, headers=None: FakeFlaskResponse(
        payload, status, headers
    )
    flask.redirect = lambda *args, **kwargs: None
    sys.modules["flask"] = flask

if "zcatalyst_sdk" not in sys.modules:
    zcatalyst_sdk = types.ModuleType("zcatalyst_sdk")
    zcatalyst_sdk.initialize = lambda: None
    sys.modules["zcatalyst_sdk"] = zcatalyst_sdk

from installations.repository import (
    INSTALLATIONS_TABLE,
    MEMBERS_TABLE,
    SOURCE_MARKETPLACE,
    SOURCE_STANDALONE,
    find_installation_by_zoho_org_id,
    find_member,
    insert_installation_row,
    insert_member_row,
)
from installations.service import (
    marketplace_zoho_installation_key,
    resolve_or_create_marketplace_installation,
)


def _quoted(query, column):
    match = re.search(rf"{re.escape(column)} = '((?:[^']|'')*)'", query)
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
        stored["ROWID"] = str(self.store.next_id)
        self.store.next_id += 1
        self.store.rows[self.name].append(stored)
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
        self.rows = {INSTALLATIONS_TABLE: [], MEMBERS_TABLE: []}

    def table(self, name):
        if name not in self.rows:
            self.rows[name] = []
        return MemoryTable(self, name)

    def execute_query(self, query):
        if f"from {INSTALLATIONS_TABLE}" in query:
            matches = list(self.rows[INSTALLATIONS_TABLE])
            org_id = _quoted(query, "zoho_org_id")
            source = _quoted(query, "source")
            key = _quoted(query, "installation_key")
            row_id = _rowid_equals(query)
            if org_id is not None:
                matches = [row for row in matches if str(row.get("zoho_org_id") or "") == org_id]
            if source is not None:
                matches = [row for row in matches if str(row.get("source") or "") == source]
            if key is not None:
                matches = [
                    row for row in matches if str(row.get("installation_key") or "") == key
                ]
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
        raise AssertionError(f"unexpected query: {query}")


class MarketplaceInstallationServiceTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()

    def test_creates_marketplace_installation_and_member(self):
        result = resolve_or_create_marketplace_installation(
            self.store,
            self.store,
            zoho_org_id="800612345",
            catalyst_user_id="user-1",
            organization_name="Acme CRM",
            zoho_user_id="zuid-1",
        )
        self.assertTrue(result["created_installation"])
        self.assertTrue(result["created_member"])
        self.assertEqual(result["installation_id"], "100")
        self.assertEqual(result["installation"]["source"], SOURCE_MARKETPLACE)
        self.assertEqual(result["installation"]["zoho_org_id"], "800612345")
        self.assertEqual(result["installation"]["organization_name"], "Acme CRM")
        self.assertEqual(
            result["installation"]["installation_key"],
            "marketplace:zoho:800612345",
        )
        self.assertEqual(result["member"]["installation_id"], "100")
        self.assertEqual(result["member"]["catalyst_user_id"], "user-1")
        self.assertEqual(result["member"]["zoho_user_id"], "zuid-1")
        self.assertEqual(len(self.store.rows[INSTALLATIONS_TABLE]), 1)
        self.assertEqual(len(self.store.rows[MEMBERS_TABLE]), 1)

    def test_reuses_existing_marketplace_installation_and_member(self):
        first = resolve_or_create_marketplace_installation(
            self.store,
            self.store,
            zoho_org_id="800612345",
            catalyst_user_id="user-1",
            organization_name="Acme CRM",
            zoho_user_id="zuid-1",
        )
        second = resolve_or_create_marketplace_installation(
            self.store,
            self.store,
            zoho_org_id="800612345",
            catalyst_user_id="user-1",
            organization_name="Acme CRM",
            zoho_user_id="zuid-1",
        )
        self.assertFalse(second["created_installation"])
        self.assertFalse(second["created_member"])
        self.assertEqual(second["installation_id"], first["installation_id"])
        self.assertEqual(second["member"]["ROWID"], first["member"]["ROWID"])
        self.assertEqual(len(self.store.rows[INSTALLATIONS_TABLE]), 1)
        self.assertEqual(len(self.store.rows[MEMBERS_TABLE]), 1)

    def test_idempotent_repeated_calls_do_not_insert(self):
        for _ in range(3):
            resolve_or_create_marketplace_installation(
                self.store,
                self.store,
                zoho_org_id="800612345",
                catalyst_user_id="user-1",
                organization_name="Acme CRM",
            )
        self.assertEqual(len(self.store.rows[INSTALLATIONS_TABLE]), 1)
        self.assertEqual(len(self.store.rows[MEMBERS_TABLE]), 1)

    def test_second_catalyst_user_reuses_marketplace_installation(self):
        first = resolve_or_create_marketplace_installation(
            self.store,
            self.store,
            zoho_org_id="800612345",
            catalyst_user_id="user-1",
            organization_name="Acme CRM",
        )
        second = resolve_or_create_marketplace_installation(
            self.store,
            self.store,
            zoho_org_id="800612345",
            catalyst_user_id="user-2",
            organization_name="Acme CRM",
            zoho_user_id="zuid-2",
        )
        self.assertFalse(second["created_installation"])
        self.assertTrue(second["created_member"])
        self.assertEqual(second["installation_id"], first["installation_id"])
        self.assertEqual(len(self.store.rows[INSTALLATIONS_TABLE]), 1)
        self.assertEqual(len(self.store.rows[MEMBERS_TABLE]), 2)
        self.assertEqual(second["member"]["catalyst_user_id"], "user-2")

    def test_does_not_reuse_standalone_installation_for_same_org(self):
        insert_installation_row(
            self.store,
            {
                "installation_key": "standalone:zoho:800612345",
                "source": SOURCE_STANDALONE,
                "zoho_org_id": "800612345",
                "organization_name": "Standalone Acme",
            },
        )
        standalone_id = self.store.rows[INSTALLATIONS_TABLE][0]["ROWID"]
        insert_member_row(
            self.store,
            {
                "installation_id": standalone_id,
                "catalyst_user_id": "owner-standalone",
            },
        )

        result = resolve_or_create_marketplace_installation(
            self.store,
            self.store,
            zoho_org_id="800612345",
            catalyst_user_id="user-1",
            organization_name="Acme CRM",
        )
        self.assertTrue(result["created_installation"])
        self.assertEqual(result["installation"]["source"], SOURCE_MARKETPLACE)
        self.assertNotEqual(result["installation_id"], standalone_id)
        self.assertEqual(len(self.store.rows[INSTALLATIONS_TABLE]), 2)
        marketplace_members = [
            row
            for row in self.store.rows[MEMBERS_TABLE]
            if row["installation_id"] == result["installation_id"]
        ]
        self.assertEqual(len(marketplace_members), 1)
        self.assertEqual(marketplace_members[0]["catalyst_user_id"], "user-1")
        standalone_members = [
            row
            for row in self.store.rows[MEMBERS_TABLE]
            if row["installation_id"] == standalone_id
        ]
        self.assertEqual(standalone_members[0]["catalyst_user_id"], "owner-standalone")
        self.assertIsNone(
            find_member(self.store, standalone_id, "user-1")
        )
        self.assertEqual(
            find_installation_by_zoho_org_id(
                self.store, "800612345", source=SOURCE_STANDALONE
            )["ROWID"],
            standalone_id,
        )

    def test_does_not_backfill_or_touch_connection_tables(self):
        result = resolve_or_create_marketplace_installation(
            self.store,
            self.store,
            zoho_org_id="800612345",
            catalyst_user_id="user-1",
        )
        self.assertEqual(result["installation_id"], "100")
        self.assertNotIn("zoho_connections", self.store.rows)
        self.assertNotIn("salesforce_connections", self.store.rows)

    def test_requires_org_and_user(self):
        with self.assertRaises(ValueError):
            resolve_or_create_marketplace_installation(
                self.store, self.store, zoho_org_id="", catalyst_user_id="user-1"
            )
        with self.assertRaises(ValueError):
            resolve_or_create_marketplace_installation(
                self.store, self.store, zoho_org_id="8001", catalyst_user_id=""
            )

    def test_marketplace_key_matches_org_id(self):
        self.assertEqual(
            marketplace_zoho_installation_key("800612345"),
            "marketplace:zoho:800612345",
        )
        with self.assertRaises(ValueError):
            marketplace_zoho_installation_key("  ")

    def test_lookup_filters_marketplace_source(self):
        queries = []

        class RecordingZcql:
            def execute_query(self, query):
                queries.append(query)
                return []

        find_installation_by_zoho_org_id(
            RecordingZcql(), "8001", source=SOURCE_MARKETPLACE
        )
        self.assertIn("zoho_org_id = '8001'", queries[0])
        self.assertIn("source = 'marketplace'", queries[0])

    def test_fills_blank_member_zoho_user_id_on_reuse(self):
        first = resolve_or_create_marketplace_installation(
            self.store,
            self.store,
            zoho_org_id="800612345",
            catalyst_user_id="user-1",
        )
        self.assertEqual(first["member"].get("zoho_user_id"), None)
        second = resolve_or_create_marketplace_installation(
            self.store,
            self.store,
            zoho_org_id="800612345",
            catalyst_user_id="user-1",
            zoho_user_id="zuid-9",
        )
        self.assertFalse(second["created_member"])
        self.assertEqual(second["member"]["zoho_user_id"], "zuid-9")
        self.assertEqual(len(self.store.rows[MEMBERS_TABLE]), 1)

    def test_updates_organization_name_on_existing_marketplace_row(self):
        resolve_or_create_marketplace_installation(
            self.store,
            self.store,
            zoho_org_id="800612345",
            catalyst_user_id="user-1",
        )
        second = resolve_or_create_marketplace_installation(
            self.store,
            self.store,
            zoho_org_id="800612345",
            catalyst_user_id="user-1",
            organization_name="Acme CRM",
        )
        self.assertFalse(second["created_installation"])
        self.assertEqual(second["installation"]["organization_name"], "Acme CRM")
        self.assertEqual(
            self.store.rows[INSTALLATIONS_TABLE][0]["organization_name"], "Acme CRM"
        )


if __name__ == "__main__":
    unittest.main()
