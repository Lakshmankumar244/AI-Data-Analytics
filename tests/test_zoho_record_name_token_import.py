import json
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

from analytics.records import _enrich_record_names
from connections import routes as connection_routes
from connections import token as connection_token


CONNECTION_ROWID = "5550000000001"
CRM_RECORD_ID = "1111111111111111111"


class TableZcql:
    def __init__(self, tables):
        self.tables = tables

    def execute_query(self, query):
        for table_name, rows in self.tables.items():
            if f"from {table_name}" in query:
                return [{table_name: row} for row in rows]
        return []


class ZohoRecordNameTokenImportTests(unittest.TestCase):
    def test_enrich_record_names_uses_token_module_not_routes(self):
        self.assertFalse(hasattr(connection_routes, "get_connection_access_token"))
        self.assertTrue(callable(connection_token.get_connection_access_token))

        scan_row = {
            "ROWID": "1001",
            "scan_id": "scan_zoho_record_names",
            "crm_provider": "zoho",
            "connection_row_id": CONNECTION_ROWID,
        }
        zcql = TableZcql(
            {
                "zoho_connections": [
                    {
                        "ROWID": CONNECTION_ROWID,
                        "access_token": "stored-token",
                    }
                ]
            }
        )
        records = [
            {
                "recordName": None,
                "recordRef": "Unnamed record",
                "module": "Accounts",
                "crmRecordId": CRM_RECORD_ID,
            }
        ]

        with patch(
            "connections.token.get_connection_access_token",
            return_value=("live-token", "https://www.zohoapis.com", False),
        ) as get_token, patch(
            "zoho.client.fetch_record_names",
            return_value={CRM_RECORD_ID: "Northwind"},
        ) as fetch_names:
            enriched = _enrich_record_names(object(), zcql, scan_row, records)

        get_token.assert_called_once()
        fetch_names.assert_called_once_with(
            "live-token",
            "https://www.zohoapis.com",
            "Accounts",
            [CRM_RECORD_ID],
        )
        self.assertEqual(enriched[0]["recordName"], "Northwind")
        self.assertNotIn("crmRecordId", enriched[0])


if __name__ == "__main__":
    unittest.main()
