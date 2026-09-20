import csv
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


FUNCTION_ROOT = (
    Path(__file__).resolve().parents[1]
    / "functions"
    / "ai_data_analytics_function"
)
WORKER_ROOT = (
    Path(__file__).resolve().parents[1]
    / "functions"
    / "ai_data_analytics_salesforce_worker"
)
ZOHO_WORKER_PROCESSING = (
    Path(__file__).resolve().parents[1]
    / "functions"
    / "ai_data_analytics_worker"
    / "pipeline"
    / "processing.py"
)
SF_WORKER_PROCESSING = WORKER_ROOT / "pipeline" / "processing.py"

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

from analytics.record_export import (
    _owner_analytics_from_bulk,
    attach_salesforce_owner_analytics,
)
from analytics.records import _owner_names
from salesforce.owner_resolution import (
    crm_user_owner_key,
    directory_lookup_keys,
    ensure_salesforce_owner_directory,
    load_salesforce_owner_directory,
    owner_field_name,
    resolve_owner_identity,
)
from salesforce.user_directory import is_salesforce_record_id


USER_ID = "005dN00000OwnerABC"
USER_ID_15 = "005dN00000AbCdE"
QUEUE_ID = "00GdN00000QueueABC"
OTHER_USER = "005dN00000OtherXYZ"
BAKAS_18 = "005dN00000BakasXYZ"
BAKAS_15 = BAKAS_18[:15]
BAKAS_18_CASE = "005DN00000BAKASXYZ"


def _write_csv(path, fieldnames, rows):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class TableZcql:
    def __init__(self, tables):
        self.tables = tables
        self.queries = []

    def execute_query(self, query):
        self.queries.append(query)
        for table_name, rows in self.tables.items():
            if f"from {table_name}" not in query:
                continue
            matched = list(rows)
            if "ROWID =" in query:
                wanted = query.split("ROWID =", 1)[1].split()[0]
                matched = [row for row in matched if str(row.get("ROWID")) == wanted]
            if "connection_row_id =" in query:
                wanted = query.split("connection_row_id =", 1)[1].split()[0]
                matched = [
                    row
                    for row in matched
                    if str(row.get("connection_row_id") or "") == wanted
                ]
            return [{table_name: row} for row in matched]
        return []


def _owner_row(crm_user_id, display_name, active=True, connection="5550000000001"):
    return {
        "crm_user_id": crm_user_id,
        "display_name": display_name,
        "active": active,
        "connection_row_id": connection,
    }


class OwnerResolutionTests(unittest.TestCase):
    def test_ownerid_resolves_to_user_display_name(self):
        directory = {crm_user_owner_key(USER_ID): "Ada Lovelace"}
        identity = resolve_owner_identity(USER_ID, directory)
        self.assertEqual(identity["ownerName"], "Ada Lovelace")
        self.assertEqual(identity["ownerId"], USER_ID)
        self.assertEqual(identity["ownerKey"], crm_user_owner_key(USER_ID))

    def test_ownerid_resolves_to_queue_display_name(self):
        directory = {crm_user_owner_key(QUEUE_ID): "Account Review Queue"}
        identity = resolve_owner_identity(QUEUE_ID, directory)
        self.assertEqual(identity["ownerName"], "Account Review Queue")
        self.assertEqual(identity["ownerId"], QUEUE_ID)

    def test_unresolved_ownerid_is_unknown_owner(self):
        identity = resolve_owner_identity(USER_ID, {})
        self.assertEqual(identity["ownerName"], "Unknown owner")
        self.assertEqual(identity["ownerKey"], crm_user_owner_key(USER_ID))

    def test_fifteen_and_eighteen_character_ids(self):
        self.assertTrue(is_salesforce_record_id(USER_ID))
        self.assertTrue(is_salesforce_record_id(USER_ID_15))
        self.assertEqual(len(USER_ID), 18)
        self.assertEqual(len(USER_ID_15), 15)
        fifteen = resolve_owner_identity(
            USER_ID_15, {crm_user_owner_key(USER_ID_15): "Fifteen User"}
        )
        eighteen = resolve_owner_identity(
            USER_ID, {crm_user_owner_key(USER_ID): "Eighteen User"}
        )
        self.assertEqual(fifteen["ownerName"], "Fifteen User")
        self.assertEqual(eighteen["ownerName"], "Eighteen User")
        self.assertNotEqual(fifteen["ownerKey"], eighteen["ownerKey"])

    def test_bulk_csv_15_char_ownerid_matches_rest_18_char_directory_id(self):
        directory = load_salesforce_owner_directory(
            TableZcql(
                {
                    "salesforce_connection_owners": [
                        _owner_row(BAKAS_18, "BAkas")
                    ]
                }
            ),
            "5550000000001",
        )
        identity = resolve_owner_identity(BAKAS_15, directory)
        self.assertEqual(identity["ownerName"], "BAkas")
        self.assertEqual(identity["ownerId"], BAKAS_15)

    def test_bulk_csv_18_char_ownerid_matches_rest_15_char_directory_id(self):
        directory = load_salesforce_owner_directory(
            TableZcql(
                {
                    "salesforce_connection_owners": [
                        _owner_row(BAKAS_15, "BAkas")
                    ]
                }
            ),
            "5550000000001",
        )
        identity = resolve_owner_identity(BAKAS_18, directory)
        self.assertEqual(identity["ownerName"], "BAkas")

    def test_ownerid_case_insensitive_15_char_prefix_matches_display_name(self):
        self.assertEqual(BAKAS_18[:15].casefold(), BAKAS_18_CASE[:15].casefold())
        directory = load_salesforce_owner_directory(
            TableZcql(
                {
                    "salesforce_connection_owners": [
                        _owner_row(BAKAS_18, "BAkas")
                    ]
                }
            ),
            "5550000000001",
        )
        identity = resolve_owner_identity(BAKAS_18_CASE, directory)
        self.assertEqual(identity["ownerName"], "BAkas")
        self.assertTrue(
            set(directory_lookup_keys(BAKAS_18_CASE))
            & set(directory_lookup_keys(BAKAS_18))
        )

    def test_directory_read_uses_select_star_not_active_column(self):
        zcql = TableZcql(
            {"salesforce_connection_owners": [_owner_row(BAKAS_18, "BAkas")]}
        )
        load_salesforce_owner_directory(zcql, "5550000000001")
        self.assertTrue(any("select *" in query for query in zcql.queries))
        self.assertFalse(
            any("select crm_user_id,display_name,active" in query for query in zcql.queries)
        )

    def test_catalyst_boolean_one_is_treated_as_active(self):
        zcql = TableZcql(
            {
                "salesforce_connection_owners": [
                    _owner_row(BAKAS_18, "BAkas", active=1)
                ]
            }
        )
        names = load_salesforce_owner_directory(zcql, "5550000000001")
        self.assertEqual(names[crm_user_owner_key(BAKAS_18)], "BAkas")

    def test_connection_specific_owner_lookup(self):
        zcql = TableZcql(
            {
                "salesforce_connection_owners": [
                    _owner_row(USER_ID, "Ada Lovelace", connection="5550000000001"),
                    _owner_row(OTHER_USER, "Wrong Connection", connection="9990000000009"),
                ]
            }
        )
        names = load_salesforce_owner_directory(zcql, "5550000000001")
        self.assertEqual(names[crm_user_owner_key(USER_ID)], "Ada Lovelace")
        self.assertNotIn(crm_user_owner_key(OTHER_USER), names)

    def test_inactive_directory_rows_are_ignored(self):
        zcql = TableZcql(
            {
                "salesforce_connection_owners": [
                    _owner_row(USER_ID, "Ada Lovelace", active=False),
                    _owner_row(QUEUE_ID, "Account Review Queue", active=True),
                ]
            }
        )
        names = load_salesforce_owner_directory(zcql, "5550000000001")
        self.assertNotIn(crm_user_owner_key(USER_ID), names)
        self.assertEqual(names[crm_user_owner_key(QUEUE_ID)], "Account Review Queue")

    def test_populated_directory_does_not_call_salesforce(self):
        zcql = TableZcql(
            {
                "salesforce_connection_owners": [
                    _owner_row(USER_ID, "Ada Lovelace")
                ]
            }
        )
        connection = {"ROWID": "5550000000001"}
        with patch(
            "salesforce.client.get_salesforce_access_token"
        ) as token, patch(
            "salesforce.owner_resolution.sync_salesforce_owner_directory"
        ) as sync:
            names = ensure_salesforce_owner_directory(
                object(), zcql, connection, refresh=False
            )
        token.assert_not_called()
        sync.assert_not_called()
        self.assertEqual(names[crm_user_owner_key(USER_ID)], "Ada Lovelace")

    def test_empty_directory_syncs_users_and_groups_once(self):
        zcql = TableZcql({"salesforce_connection_owners": []})
        connection = {"ROWID": "5550000000001"}

        def _sync(*args, **kwargs):
            del args, kwargs
            zcql.tables["salesforce_connection_owners"] = [
                _owner_row(USER_ID, "Ada Lovelace")
            ]

        with patch(
            "salesforce.client.get_salesforce_access_token",
            return_value=("token", "https://example.my.salesforce.com"),
        ) as token, patch(
            "salesforce.owner_resolution.sync_salesforce_owner_directory",
            side_effect=_sync,
        ) as sync:
            names = ensure_salesforce_owner_directory(
                object(), zcql, connection, refresh=False
            )
        token.assert_called_once()
        sync.assert_called_once()
        self.assertEqual(names[crm_user_owner_key(USER_ID)], "Ada Lovelace")

    def test_failed_sync_is_not_treated_as_a_populated_directory(self):
        zcql = TableZcql({"salesforce_connection_owners": []})
        connection = {"ROWID": "48465000000182004"}
        with patch(
            "salesforce.client.get_salesforce_access_token",
            return_value=("token", "https://example.my.salesforce.com"),
        ), patch(
            "salesforce.owner_resolution.sync_salesforce_owner_directory",
            return_value={
                "refreshed": False,
                "apiCalls": 1,
                "counts": {"user": 0, "queue": 0, "group": 0},
                "warning": "Salesforce owner directory cache could not be stored",
            },
        ), self.assertLogs("salesforce.owner_resolution", level="WARNING") as logs:
            names = ensure_salesforce_owner_directory(
                object(), zcql, connection, refresh=False
            )
        self.assertEqual(names, {})
        self.assertTrue(
            any("did not persist owners" in message for message in logs.output)
        )

    def test_owner_field_prefers_zoho_owner_then_salesforce_ownerid(self):
        self.assertEqual(owner_field_name(["id", "Owner", "Created_Time"]), "Owner")
        self.assertEqual(owner_field_name(["Id", "OwnerId", "CreatedDate"]), "OwnerId")
        self.assertIsNone(owner_field_name(["Id", "Name"]))

    def test_zoho_json_owner_identity_is_unchanged(self):
        identity = resolve_owner_identity(
            json.dumps({"id": "333", "name": "Pat Lee"}),
            {},
        )
        self.assertEqual(identity["ownerName"], "Pat Lee")
        self.assertEqual(identity["ownerId"], "333")
        self.assertEqual(identity["ownerKey"], crm_user_owner_key("333"))


class OwnerAnalyticsContractTests(unittest.TestCase):
    def test_salesforce_owner_csv_builds_owner_quality_payload(self):
        handle = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
        handle.close()
        field_names = ["Id", "OwnerId", "CreatedDate", "Name"]
        _write_csv(
            handle.name,
            field_names,
            [
                {
                    "Id": "001dN00000AbCdEFGH",
                    "OwnerId": USER_ID,
                    "CreatedDate": "2024-03-01T08:15:00.000+0000",
                    "Name": "Acme Manufacturing",
                },
                {
                    "Id": "001dN00000AbCdEFGI",
                    "OwnerId": QUEUE_ID,
                    "CreatedDate": "2024-03-02T08:15:00.000+0000",
                    "Name": "Queued Account",
                },
            ],
        )
        module_row = {
            "ROWID": "2001",
            "module_api_name": "Account",
            "field_allowlist_json": json.dumps(field_names),
            "field_metadata_json": json.dumps(
                [{"apiName": name, "label": name} for name in field_names]
            ),
        }
        directory = {
            crm_user_owner_key(USER_ID): "Ada Lovelace",
            crm_user_owner_key(QUEUE_ID): "Account Review Queue",
        }
        with patch(
            "analytics.record_export._download_source_zip",
            return_value=handle.name,
        ):
            entries = _owner_analytics_from_bulk(
                {"source_file_id": "9", "source_file_checksum": "abc"},
                module_row,
                {"scan_id": "scan_1f09354578c7422c82d8f18d8a161052", "depth_policy": "quick"},
                directory,
            )
        by_name = {entry["data"]["ownerName"]: entry["data"] for entry in entries}
        self.assertEqual(set(by_name), {"Account Review Queue", "Ada Lovelace"})
        ada = by_name["Ada Lovelace"]
        self.assertEqual(ada["recordCount"], 1)
        self.assertGreater(ada["totalCells"], 0)
        self.assertIn("completenessRate", ada)
        self.assertIn("validityRate", ada)
        self.assertEqual(ada["ownerKey"], crm_user_owner_key(USER_ID))
        self.assertNotIn("ownerId", ada)
        self.assertEqual(entries[0]["schemaVersion"], "owner-quality-v2")

    def test_owner_analytics_uses_directory_name_for_15_18_ownerid_mismatch(self):
        handle = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
        handle.close()
        field_names = ["Id", "OwnerId", "CreatedDate", "Name"]
        _write_csv(
            handle.name,
            field_names,
            [
                {
                    "Id": "001dN00000AbCdEFGH",
                    "OwnerId": BAKAS_15,
                    "CreatedDate": "2024-03-01T08:15:00.000+0000",
                    "Name": "Acme Manufacturing",
                }
            ],
        )
        module_row = {
            "ROWID": "2001",
            "module_api_name": "Account",
            "field_allowlist_json": json.dumps(field_names),
            "field_metadata_json": json.dumps(
                [{"apiName": name, "label": name} for name in field_names]
            ),
        }
        directory = load_salesforce_owner_directory(
            TableZcql(
                {
                    "salesforce_connection_owners": [
                        _owner_row(BAKAS_18, "BAkas")
                    ]
                }
            ),
            "5550000000001",
        )
        with patch(
            "analytics.record_export._download_source_zip",
            return_value=handle.name,
        ):
            entries = _owner_analytics_from_bulk(
                {"source_file_id": "9", "source_file_checksum": "abc"},
                module_row,
                {
                    "scan_id": "scan_1f09354578c7422c82d8f18d8a161052",
                    "depth_policy": "quick",
                },
                directory,
            )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["data"]["ownerName"], "BAkas")
        self.assertEqual(entries[0]["data"]["recordCount"], 1)

    def test_attach_fills_empty_salesforce_owner_analytics(self):
        payload = {
            "modules": [
                {
                    "moduleApiName": "Account",
                    "ownerAnalytics": [],
                    "metrics": {},
                }
            ]
        }
        rebuilt = [
            {
                "schemaVersion": "owner-quality-v2",
                "ruleVersion": "quality-rules-v1",
                "resultChecksum": "abc",
                "computedAt": "",
                "data": {
                    "ownerKey": crm_user_owner_key(USER_ID),
                    "ownerName": "Ada Lovelace",
                    "recordCount": 5,
                    "totalCells": 20,
                    "populatedCells": 18,
                    "checkedValues": 4,
                    "invalidValues": 0,
                    "emptyCells": 2,
                    "completenessRate": 0.9,
                    "validityRate": 1.0,
                },
            }
        ]
        zcql = TableZcql(
            {
                "salesforce_connections": [{"ROWID": "5550000000001"}],
                "salesforce_connection_owners": [_owner_row(USER_ID, "Ada Lovelace")],
            }
        )
        scan_row = {
            "crm_provider": "salesforce",
            "connection_row_id": "5550000000001",
            "ROWID": "1001",
        }
        with patch(
            "analytics.record_export.list_owner_analytics",
            return_value=rebuilt,
        ) as listed:
            attach_salesforce_owner_analytics(object(), zcql, scan_row, payload)
        listed.assert_called_once()
        self.assertEqual(payload["modules"][0]["ownerAnalytics"][0]["data"]["ownerName"], "Ada Lovelace")
        self.assertEqual(payload["modules"][0]["ownerAnalytics"][0]["data"]["recordCount"], 5)

    def test_attach_does_not_change_zoho_results(self):
        payload = {
            "modules": [
                {
                    "moduleApiName": "Accounts",
                    "ownerAnalytics": [],
                    "metrics": {},
                }
            ]
        }
        with patch("analytics.record_export.list_owner_analytics") as listed:
            attach_salesforce_owner_analytics(
                object(),
                TableZcql({}),
                {"crm_provider": "zoho", "connection_row_id": "1", "ROWID": "1"},
                payload,
            )
        listed.assert_not_called()
        self.assertEqual(payload["modules"][0]["ownerAnalytics"], [])

    def test_records_owner_names_use_shared_salesforce_directory(self):
        zcql = TableZcql(
            {
                "salesforce_connection_owners": [
                    _owner_row(USER_ID, "Ada Lovelace"),
                    _owner_row(QUEUE_ID, "Account Review Queue"),
                ],
                "zoho_connection_users": [
                    {"crm_user_key": "should-not-be-used", "display_name": "Zoho"}
                ],
            }
        )
        names = _owner_names(
            zcql,
            {
                "crm_provider": "salesforce",
                "connection_row_id": "5550000000001",
            },
        )
        self.assertEqual(names[crm_user_owner_key(USER_ID)], "Ada Lovelace")
        self.assertEqual(names[crm_user_owner_key(QUEUE_ID)], "Account Review Queue")
        self.assertFalse(any("zoho_connection_users" in query for query in zcql.queries))

    def test_zoho_owner_names_still_use_zoho_connection_users(self):
        zcql = TableZcql(
            {
                "zoho_connection_users": [
                    {
                        "crm_user_key": "abc123",
                        "display_name": "Pat Lee",
                        "connection_row_id": "5550000000001",
                    }
                ]
            }
        )
        names = _owner_names(
            zcql, {"crm_provider": "zoho", "connection_row_id": "5550000000001"}
        )
        self.assertEqual(names["abc123"], "Pat Lee")
        self.assertTrue(any("zoho_connection_users" in query for query in zcql.queries))
        self.assertFalse(
            any("salesforce_connection_owners" in query for query in zcql.queries)
        )


class ZohoPathUnchangedTests(unittest.TestCase):
    def test_zoho_worker_still_uses_owner_and_zoho_directory(self):
        source = ZOHO_WORKER_PROCESSING.read_text(encoding="utf-8")
        self.assertIn('if "Owner" in field_names:', source)
        self.assertIn('owner_field_available = "Owner" in header_mapping', source)
        self.assertIn("zoho_connection_users", source)
        self.assertNotIn("salesforce_connection_owners", source)
        self.assertNotIn("OwnerId", source)

    def test_salesforce_worker_uses_shared_owner_resolution(self):
        source = SF_WORKER_PROCESSING.read_text(encoding="utf-8")
        self.assertIn("from salesforce.owner_resolution import", source)
        self.assertIn("owner_field_name(field_names)", source)
        self.assertIn("load_salesforce_owner_directory", source)
        self.assertIn("ensure_salesforce_owner_directory", source)
        self.assertNotIn("zoho_connection_users", source)
        self.assertNotIn('if "Owner" in field_names:', source)


if __name__ == "__main__":
    unittest.main()
