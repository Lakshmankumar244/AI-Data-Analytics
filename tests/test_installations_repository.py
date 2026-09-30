import sys
import types
import unittest
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
                import json

                return json.loads(self.payload.decode("utf-8"))
            if isinstance(self.payload, str):
                import json

                return json.loads(self.payload)
            return self.payload

    flask.make_response = lambda payload, status=200, headers=None: FakeFlaskResponse(
        payload, status, headers
    )
    flask.redirect = lambda *args, **kwargs: None
    sys.modules["flask"] = flask

if "zcatalyst_sdk" not in sys.modules:
    zcatalyst_sdk = types.ModuleType("zcatalyst_sdk")
    zcatalyst_sdk.initialize = lambda: None
    sys.modules["zcatalyst_sdk"] = zcatalyst_sdk

from installations.models import installation_from_row, member_from_row
from installations.repository import (
    INSTALLATION_ID_COLUMN,
    INSTALLATIONS_TABLE,
    MEMBERS_TABLE,
    SALESFORCE_CONNECTIONS_TABLE,
    SOURCE_STANDALONE,
    STATUS_ACTIVE,
    ZOHO_CONNECTIONS_TABLE,
    connection_installation_id,
    connection_row_for_persist,
    find_installation_by_key,
    find_installation_by_row_id,
    find_installation_by_salesforce_org_id,
    find_installation_by_zoho_org_id,
    find_member,
    find_members_for_installation,
    find_memberships_for_user,
    find_salesforce_connections_by_installation,
    find_zoho_connections_by_installation,
    insert_installation_row,
    insert_member_row,
    installation_persist_fields,
    member_persist_fields,
    normalize_installation_id,
    set_connection_installation_id,
    update_installation_row,
    with_optional_installation_id,
)
from connections.routes import upsert_connection
from salesforce.oauth import upsert_salesforce_connection


class FakeQuery:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.queries = []

    def execute_query(self, query):
        self.queries.append(query)
        return self.rows


class FakeTable:
    def __init__(self, name):
        self.name = name
        self.inserted = []
        self.updated = []

    def insert_row(self, row):
        stored = {"ROWID": "9001", **row}
        self.inserted.append(row)
        return stored

    def update_row(self, row):
        self.updated.append(row)
        return row


class FakeDatastore:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        if name not in self.tables:
            self.tables[name] = FakeTable(name)
        return self.tables[name]


class InstallationIdHelpersTests(unittest.TestCase):
    def test_blank_installation_id_is_none(self):
        self.assertIsNone(normalize_installation_id(None))
        self.assertIsNone(normalize_installation_id(""))
        self.assertIsNone(normalize_installation_id("  "))
        self.assertIsNone(normalize_installation_id("inst_abc"))

    def test_numeric_and_nested_rowid_are_kept(self):
        self.assertEqual(normalize_installation_id("48465000000000001"), "48465000000000001")
        self.assertEqual(
            normalize_installation_id({"ROWID": "48465000000000002"}),
            "48465000000000002",
        )

    def test_connection_row_without_installation_id_reads_none(self):
        self.assertIsNone(connection_installation_id({"ROWID": "1", "user_id": "u1"}))
        self.assertIsNone(connection_installation_id({"installation_id": ""}))
        self.assertIsNone(connection_installation_id(None))

    def test_connection_row_with_installation_id_reads_rowid(self):
        self.assertEqual(
            connection_installation_id({"installation_id": "48465000000000003"}),
            "48465000000000003",
        )

    def test_optional_payload_omits_missing_and_blank_installation_id(self):
        self.assertEqual(with_optional_installation_id({"status": "connected"}), {"status": "connected"})
        self.assertEqual(
            with_optional_installation_id({"installation_id": ""}),
            {},
        )
        self.assertEqual(
            with_optional_installation_id({"installation_id": None, "user_id": "u1"}),
            {"user_id": "u1"},
        )

    def test_optional_payload_keeps_numeric_installation_id(self):
        self.assertEqual(
            with_optional_installation_id({"installation_id": "11", "user_id": "u1"}),
            {"installation_id": "11", "user_id": "u1"},
        )

    def test_connection_persist_without_installation_id_does_not_add_column(self):
        payload = connection_row_for_persist(
            "user-1",
            {"zoho_org_id": "org-1", "status": "connected"},
        )
        self.assertEqual(payload["user_id"], "user-1")
        self.assertNotIn(INSTALLATION_ID_COLUMN, payload)

    def test_connection_persist_accepts_installation_id(self):
        payload = connection_row_for_persist(
            "user-1",
            {"zoho_org_id": "org-1", "installation_id": "22"},
        )
        self.assertEqual(payload[INSTALLATION_ID_COLUMN], "22")


class InstallationRepositoryTests(unittest.TestCase):
    def test_persist_fields_require_key_and_source(self):
        with self.assertRaises(ValueError):
            installation_persist_fields({"source": SOURCE_STANDALONE})
        with self.assertRaises(ValueError):
            installation_persist_fields({"installation_key": "inst_1"})

    def test_persist_fields_omit_empty_org_columns(self):
        row = installation_persist_fields(
            {
                "installation_key": "inst_1",
                "source": SOURCE_STANDALONE,
                "zoho_org_id": "",
                "salesforce_org_id": None,
            }
        )
        self.assertEqual(row["status"], STATUS_ACTIVE)
        self.assertNotIn("zoho_org_id", row)
        self.assertNotIn("salesforce_org_id", row)
        self.assertNotIn("organization_name", row)

    def test_insert_installation_row_writes_caller_fields_only(self):
        datastore = FakeDatastore()
        inserted = insert_installation_row(
            datastore,
            {
                "installation_key": "inst_1",
                "source": SOURCE_STANDALONE,
                "zoho_org_id": "8001",
                "organization_name": "Acme",
            },
        )
        table = datastore.tables[INSTALLATIONS_TABLE]
        self.assertEqual(table.inserted[0]["installation_key"], "inst_1")
        self.assertEqual(table.inserted[0]["zoho_org_id"], "8001")
        self.assertEqual(inserted["ROWID"], "9001")

    def test_find_installation_by_row_id_skips_invalid_ids(self):
        zcql = FakeQuery()
        self.assertIsNone(find_installation_by_row_id(zcql, "abc"))
        self.assertEqual(zcql.queries, [])

    def test_find_installation_queries_use_table_and_escape(self):
        zcql = FakeQuery(
            [{"marketplace_installations": {"ROWID": "1", "installation_key": "k"}}]
        )
        row = find_installation_by_key(zcql, "o'reilly")
        self.assertEqual(row["installation_key"], "k")
        self.assertIn("marketplace_installations", zcql.queries[0])
        self.assertIn("o''reilly", zcql.queries[0])

        zcql = FakeQuery([{"marketplace_installations": {"ROWID": "2"}}])
        self.assertEqual(find_installation_by_zoho_org_id(zcql, "org-9")["ROWID"], "2")
        self.assertIn("zoho_org_id = 'org-9'", zcql.queries[0])

        zcql = FakeQuery([{"marketplace_installations": {"ROWID": "3"}}])
        self.assertEqual(
            find_installation_by_salesforce_org_id(zcql, "00Dxx")["ROWID"], "3"
        )

    def test_member_persist_and_lookup(self):
        fields = member_persist_fields(
            {
                "installation_id": "55",
                "catalyst_user_id": "user-1",
                "zoho_user_id": "zuid-1",
            }
        )
        self.assertEqual(fields["installation_id"], "55")
        self.assertEqual(fields["catalyst_user_id"], "user-1")
        self.assertEqual(fields["status"], STATUS_ACTIVE)

        datastore = FakeDatastore()
        insert_member_row(datastore, fields)
        self.assertEqual(datastore.tables[MEMBERS_TABLE].inserted[0]["installation_id"], "55")

        zcql = FakeQuery(
            [
                {
                    "installation_members": {
                        "ROWID": "8",
                        "installation_id": "55",
                        "catalyst_user_id": "user-1",
                    }
                }
            ]
        )
        member = find_member(zcql, "55", "user-1")
        self.assertEqual(member["ROWID"], "8")
        self.assertEqual(find_members_for_installation(zcql, "55")[0]["ROWID"], "8")
        self.assertEqual(find_memberships_for_user(zcql, "user-1")[0]["ROWID"], "8")

    def test_namedtuples_map_datastore_rows(self):
        installation = installation_from_row(
            {
                "ROWID": "1",
                "installation_key": "inst_1",
                "source": SOURCE_STANDALONE,
                "status": STATUS_ACTIVE,
            }
        )
        self.assertEqual(installation.row_id, "1")
        self.assertEqual(installation.zoho_org_id, "")
        member = member_from_row(
            {
                "ROWID": "2",
                "installation_id": "1",
                "catalyst_user_id": "u1",
            }
        )
        self.assertEqual(member.catalyst_user_id, "u1")
        self.assertEqual(member.zoho_user_id, "")

    def test_set_connection_installation_id_updates_supported_tables(self):
        datastore = FakeDatastore()
        set_connection_installation_id(
            datastore, ZOHO_CONNECTIONS_TABLE, "101", "55"
        )
        set_connection_installation_id(
            datastore, SALESFORCE_CONNECTIONS_TABLE, {"ROWID": "202"}, "55"
        )
        self.assertEqual(
            datastore.tables[ZOHO_CONNECTIONS_TABLE].updated[0],
            {"ROWID": "101", "installation_id": "55"},
        )
        self.assertEqual(
            datastore.tables[SALESFORCE_CONNECTIONS_TABLE].updated[0],
            {"ROWID": "202", "installation_id": "55"},
        )
        with self.assertRaises(ValueError):
            set_connection_installation_id(datastore, "scan_jobs", "1", "55")
        with self.assertRaises(ValueError):
            set_connection_installation_id(
                datastore, ZOHO_CONNECTIONS_TABLE, "101", ""
            )

    def test_find_connections_by_installation(self):
        zcql = FakeQuery([{"zoho_connections": {"ROWID": "101"}}])
        rows = find_zoho_connections_by_installation(zcql, "55")
        self.assertEqual(rows[0]["ROWID"], "101")
        self.assertIn("installation_id = '55'", zcql.queries[0])

        zcql = FakeQuery([{"salesforce_connections": {"ROWID": "202"}}])
        rows = find_salesforce_connections_by_installation(zcql, "55")
        self.assertEqual(rows[0]["ROWID"], "202")

    def test_update_installation_row_requires_valid_id(self):
        datastore = FakeDatastore()
        with self.assertRaises(ValueError):
            update_installation_row(datastore, "nope", {"status": "disabled"})
        update_installation_row(datastore, "9", {"organization_name": "Renamed"})
        self.assertEqual(
            datastore.tables[INSTALLATIONS_TABLE].updated[0]["organization_name"],
            "Renamed",
        )


class ConnectionUpsertInstallationIdTests(unittest.TestCase):
    def test_zoho_upsert_omits_installation_id_when_oauth_fields_omit_it(self):
        datastore = FakeDatastore()
        zcql = FakeQuery([])
        with patch("connections.routes.zcatalyst_sdk") as sdk:
            sdk.initialize.return_value.zcql.return_value = zcql
            upsert_connection(
                datastore,
                "user-1",
                {
                    "zoho_org_id": "org-1",
                    "zoho_user_id": "zuid-1",
                    "status": "connected",
                    "is_active": True,
                },
            )
        inserted = datastore.tables["zoho_connections"].inserted[0]
        self.assertNotIn("installation_id", inserted)
        self.assertEqual(inserted["user_id"], "user-1")

    def test_zoho_upsert_persists_explicit_installation_id(self):
        datastore = FakeDatastore()
        zcql = FakeQuery([])
        with patch("connections.routes.zcatalyst_sdk") as sdk:
            sdk.initialize.return_value.zcql.return_value = zcql
            upsert_connection(
                datastore,
                "user-1",
                {
                    "zoho_org_id": "org-1",
                    "zoho_user_id": "zuid-1",
                    "installation_id": "55",
                    "status": "connected",
                },
            )
        inserted = datastore.tables["zoho_connections"].inserted[0]
        self.assertEqual(inserted["installation_id"], "55")

    def test_zoho_upsert_does_not_write_blank_installation_id_on_update(self):
        datastore = FakeDatastore()
        existing = {
            "ROWID": "101",
            "zoho_org_id": "org-1",
            "zoho_user_id": "zuid-1",
            "installation_id": "55",
            "is_active": False,
        }
        zcql = FakeQuery([{"zoho_connections": existing}])
        with patch("connections.routes.zcatalyst_sdk") as sdk:
            sdk.initialize.return_value.zcql.return_value = zcql
            upsert_connection(
                datastore,
                "user-1",
                {
                    "zoho_org_id": "org-1",
                    "zoho_user_id": "zuid-1",
                    "installation_id": "",
                    "status": "connected",
                },
            )
        updated = datastore.tables["zoho_connections"].updated[0]
        self.assertNotIn("installation_id", updated)
        self.assertEqual(updated["ROWID"], "101")

    def test_salesforce_upsert_omits_installation_id_by_default(self):
        datastore = FakeDatastore()
        zcql = FakeQuery([])
        with patch("salesforce.oauth.zcatalyst_sdk") as sdk:
            sdk.initialize.return_value.zcql.return_value = zcql
            with patch("salesforce.oauth.activate_exclusive_connection"):
                upsert_salesforce_connection(
                    datastore,
                    "user-1",
                    {
                        "salesforce_org_id": "00Dxx",
                        "salesforce_user_id": "005xx",
                        "status": "connected",
                    },
                )
        inserted = datastore.tables[SALESFORCE_CONNECTIONS_TABLE].inserted[0]
        self.assertNotIn("installation_id", inserted)

    def test_salesforce_upsert_persists_explicit_installation_id(self):
        datastore = FakeDatastore()
        zcql = FakeQuery([])
        with patch("salesforce.oauth.zcatalyst_sdk") as sdk:
            sdk.initialize.return_value.zcql.return_value = zcql
            with patch("salesforce.oauth.activate_exclusive_connection"):
                upsert_salesforce_connection(
                    datastore,
                    "user-1",
                    {
                        "salesforce_org_id": "00Dxx",
                        "salesforce_user_id": "005xx",
                        "installation_id": "55",
                        "status": "connected",
                    },
                )
        inserted = datastore.tables[SALESFORCE_CONNECTIONS_TABLE].inserted[0]
        self.assertEqual(inserted["installation_id"], "55")


if __name__ == "__main__":
    unittest.main()
