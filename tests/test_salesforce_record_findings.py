import csv
import io
import json
import sys
import tempfile
import types
import unittest
import zipfile
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
            return json.loads(self.payload)

    flask.make_response = lambda payload, status=200, headers=None: FakeFlaskResponse(
        payload, status, headers
    )
    flask.redirect = lambda *args, **kwargs: None
    sys.modules["flask"] = flask

if "zcatalyst_sdk" not in sys.modules:
    zcatalyst_sdk = types.ModuleType("zcatalyst_sdk")
    zcatalyst_sdk.initialize = lambda: None
    sys.modules["zcatalyst_sdk"] = zcatalyst_sdk

from analytics.record_export import _clean_records_from_bulk, _owner_identity
from analytics.records import (
    _connection_row,
    _enrich_record_names,
    _owner_names,
    _safe_crm_record_id,
    get_record_findings,
)
from common.core import canonical_hash
from salesforce.user_directory import is_salesforce_record_id


ACCOUNT_ID = "001dN00000AbCdEFGH"
ACCOUNT_ID_15 = "001dN00000AbCdE"
OWNER_ID = "005dN00000OwnerABC"
CREATED = "2024-03-01T08:15:00.000+0000"


def _write_csv(path, fieldnames, rows):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_zip_csv(path, fieldnames, rows):
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("Accounts.csv", buffer.getvalue())


def _module_row(field_names, module_api_name="Account"):
    return {
        "ROWID": "2001",
        "module_api_name": module_api_name,
        "field_allowlist_json": json.dumps(field_names),
        "field_metadata_json": json.dumps(
            [{"apiName": name, "label": name} for name in field_names]
        ),
    }


def _scan_row(provider="salesforce"):
    return {
        "ROWID": "1001",
        "scan_id": "scan_1f09354578c7422c82d8f18d8a161052",
        "crm_provider": provider,
        "connection_row_id": "5550000000001",
        "depth_policy": "quick",
    }


class TableZcql:
    def __init__(self, tables):
        self.tables = tables
        self.queries = []

    def execute_query(self, query):
        self.queries.append(query)
        for table_name, rows in self.tables.items():
            if f"from {table_name}" in query:
                return [{table_name: row} for row in rows]
        return []


class RecordExportTests(unittest.TestCase):
    def _clean_from_path(self, path, field_names, scan_row=None, owner_directory=None):
        scan_row = scan_row or _scan_row()
        module_row = _module_row(field_names)
        with patch(
            "analytics.record_export._download_source_zip",
            return_value=path,
        ):
            return _clean_records_from_bulk(
                {"source_file_id": "9", "source_file_checksum": "abc"},
                module_row,
                scan_row,
                owner_directory or {},
                [],
            )

    def test_zoho_zip_still_lists_clean_records(self):
        handle = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        handle.close()
        _write_zip_csv(
            handle.name,
            ["id", "Owner", "Created_Time", "Account_Name"],
            [
                {
                    "id": "1111111111111111111",
                    "Owner": json.dumps({"id": "333", "name": "Pat Lee"}),
                    "Created_Time": "2024-03-01 08:15:00",
                    "Account_Name": "Northwind",
                }
            ],
        )
        records = self._clean_from_path(
            handle.name,
            ["id", "Owner", "Created_Time", "Account_Name"],
            _scan_row("zoho"),
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["recordName"], "Northwind")
        self.assertEqual(records[0]["ownerName"], "Pat Lee")
        self.assertIn("2024-03-01", records[0]["createdTime"])
        self.assertEqual(records[0]["state"], "proper")

    def test_salesforce_csv_lists_id_ownerid_createddate_and_name(self):
        handle = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
        handle.close()
        owner_key = canonical_hash({"crm_user_id": OWNER_ID})
        _write_csv(
            handle.name,
            ["Id", "OwnerId", "CreatedDate", "Name"],
            [
                {
                    "Id": ACCOUNT_ID,
                    "OwnerId": OWNER_ID,
                    "CreatedDate": CREATED,
                    "Name": "Acme Manufacturing",
                }
            ],
        )
        records = self._clean_from_path(
            handle.name,
            ["Id", "OwnerId", "CreatedDate", "Name"],
            owner_directory={owner_key: "Ada Lovelace"},
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["recordName"], "Acme Manufacturing")
        self.assertEqual(records[0]["recordRef"], "Acme Manufacturing")
        self.assertEqual(records[0]["ownerName"], "Ada Lovelace")
        self.assertEqual(records[0]["createdTime"], CREATED)
        self.assertTrue(records[0]["findingId"].startswith("clean_"))

    def test_csv_with_zoho_id_owner_and_created_time_aliases(self):
        handle = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
        handle.close()
        _write_csv(
            handle.name,
            ["id", "Owner", "Created_Time", "Name"],
            [
                {
                    "id": ACCOUNT_ID_15,
                    "Owner": OWNER_ID,
                    "Created_Time": "2024-03-01 08:15:00",
                    "Name": "Fifteen Char Account",
                }
            ],
        )
        records = self._clean_from_path(
            handle.name,
            ["id", "Owner", "Created_Time", "Name"],
            owner_directory={
                canonical_hash({"crm_user_id": OWNER_ID}): "Ada Lovelace"
            },
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["recordName"], "Fifteen Char Account")
        self.assertEqual(records[0]["ownerName"], "Ada Lovelace")
        self.assertIn("2024-03-01", records[0]["createdTime"])

    def test_salesforce_alphanumeric_owner_id_is_not_treated_as_a_name(self):
        identity = _owner_identity(OWNER_ID, {})
        self.assertEqual(identity["ownerName"], "Unknown owner")
        self.assertEqual(
            identity["ownerKey"], canonical_hash({"crm_user_id": OWNER_ID})
        )

    def test_zoho_numeric_owner_id_is_unchanged(self):
        identity = _owner_identity("555666777", {"not": "used"})
        self.assertEqual(
            identity["ownerKey"], canonical_hash({"crm_user_id": "555666777"})
        )


class RecordLookupTests(unittest.TestCase):
    def test_safe_crm_record_id_keeps_salesforce_and_zoho_ids(self):
        self.assertEqual(_safe_crm_record_id("1234567890123456789"), "1234567890123456789")
        self.assertEqual(_safe_crm_record_id(ACCOUNT_ID), ACCOUNT_ID)
        self.assertEqual(_safe_crm_record_id(ACCOUNT_ID_15), ACCOUNT_ID_15)
        self.assertTrue(is_salesforce_record_id(ACCOUNT_ID))
        self.assertTrue(is_salesforce_record_id(ACCOUNT_ID_15))
        self.assertEqual(_safe_crm_record_id("not-an-id"), "")

    def test_salesforce_connection_lookup_does_not_query_zoho(self):
        zcql = TableZcql(
            {
                "salesforce_connections": [{"ROWID": "5550000000001", "status": "connected"}],
                "zoho_connections": [{"ROWID": "5550000000001"}],
            }
        )
        row = _connection_row(zcql, _scan_row("salesforce"))
        self.assertEqual(row["ROWID"], "5550000000001")
        self.assertTrue(any("salesforce_connections" in query for query in zcql.queries))
        self.assertFalse(any("zoho_connections" in query for query in zcql.queries))

    def test_zoho_connection_lookup_does_not_query_salesforce(self):
        zcql = TableZcql(
            {
                "zoho_connections": [{"ROWID": "5550000000001", "status": "connected"}],
                "salesforce_connections": [{"ROWID": "5550000000001"}],
            }
        )
        row = _connection_row(zcql, _scan_row("zoho"))
        self.assertEqual(row["status"], "connected")
        self.assertTrue(any("zoho_connections" in query for query in zcql.queries))
        self.assertFalse(any("salesforce_connections" in query for query in zcql.queries))

    def test_salesforce_owner_lookup_hashes_crm_user_id(self):
        zcql = TableZcql(
            {
                "salesforce_connection_owners": [
                    {
                        "crm_user_id": OWNER_ID,
                        "display_name": "Ada Lovelace",
                        "active": True,
                    },
                    {
                        "crm_user_id": "005dN00000InactiveAB",
                        "display_name": "Inactive",
                        "active": False,
                    },
                ],
                "zoho_connection_users": [
                    {"crm_user_key": "should-not-be-used", "display_name": "Zoho"}
                ],
            }
        )
        names = _owner_names(zcql, _scan_row("salesforce"))
        self.assertEqual(
            names[canonical_hash({"crm_user_id": OWNER_ID})], "Ada Lovelace"
        )
        self.assertNotIn(canonical_hash({"crm_user_id": "005dN00000InactiveAB"}), names)
        self.assertTrue(
            any("salesforce_connection_owners" in query for query in zcql.queries)
        )
        self.assertFalse(any("zoho_connection_users" in query for query in zcql.queries))

    def test_zoho_owner_lookup_still_uses_crm_user_key(self):
        zcql = TableZcql(
            {
                "zoho_connection_users": [
                    {"crm_user_key": "abc123", "display_name": "Pat Lee"}
                ]
            }
        )
        names = _owner_names(zcql, _scan_row("zoho"))
        self.assertEqual(names["abc123"], "Pat Lee")
        self.assertTrue(any("zoho_connection_users" in query for query in zcql.queries))

    def test_salesforce_enrichment_keeps_account_name_and_skips_zoho_fetch(self):
        records = [
            {
                "recordName": "Acme Manufacturing",
                "recordRef": "Acme Manufacturing",
                "module": "Account",
                "crmRecordId": ACCOUNT_ID,
            }
        ]
        with patch("zoho.client.fetch_record_names") as fetch_names:
            enriched = _enrich_record_names(
                object(), TableZcql({}), _scan_row("salesforce"), records
            )
        fetch_names.assert_not_called()
        self.assertEqual(enriched[0]["recordName"], "Acme Manufacturing")
        self.assertNotIn("crmRecordId", enriched[0])

    def test_salesforce_enrichment_does_not_call_zoho_when_name_is_missing(self):
        records = [
            {
                "recordName": None,
                "recordRef": "Unnamed record",
                "module": "Account",
                "crmRecordId": ACCOUNT_ID,
            }
        ]
        with patch("zoho.client.fetch_record_names") as fetch_names:
            enriched = _enrich_record_names(
                object(), TableZcql({}), _scan_row("salesforce"), records
            )
        fetch_names.assert_not_called()
        self.assertIsNone(enriched[0]["recordName"])
        self.assertNotIn("crmRecordId", enriched[0])


class RecordFindingsRouteTests(unittest.TestCase):
    def test_genuine_read_failure_still_returns_record_findings_read_failed(self):
        captured = {}

        def fake_json_response(payload, status=200):
            captured["payload"] = payload
            captured["status"] = status
            return types.SimpleNamespace(status_code=status, payload=payload)

        request = types.SimpleNamespace(
            args=types.SimpleNamespace(
                get=lambda key, default=None: default,
                getlist=lambda key: [],
            )
        )
        with patch(
            "analytics.records.json_response", side_effect=fake_json_response
        ), patch(
            "analytics.records.get_current_user_id", return_value="user-1"
        ), patch(
            "analytics.records.find_owned_scan",
            return_value=_scan_row("salesforce"),
        ), patch(
            "analytics.records.find_analytics_results",
            side_effect=RuntimeError("datastore down"),
        ), patch("analytics.records.zcatalyst_sdk.initialize") as initialize:
            initialize.return_value.zcql.return_value = object()
            response = get_record_findings(request, object(), _scan_row()["scan_id"])
        self.assertEqual(response.status_code, 500)
        self.assertEqual(captured["status"], 500)
        self.assertEqual(
            captured["payload"]["error"]["code"], "RECORD_FINDINGS_READ_FAILED"
        )
        self.assertEqual(
            captured["payload"]["error"]["message"],
            "Record findings could not be read",
        )


if __name__ == "__main__":
    unittest.main()
