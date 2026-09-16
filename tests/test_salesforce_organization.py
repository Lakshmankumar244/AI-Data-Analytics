import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import requests


FUNCTION_ROOT = (
    Path(__file__).resolve().parents[1]
    / "functions"
    / "ai_data_analytics_function"
)
sys.path.insert(0, str(FUNCTION_ROOT))

from salesforce.client import (
    SALESFORCE_CONNECTIONS_TABLE,
    SALESFORCE_ORGANIZATION_QUERY,
    fetch_salesforce_organization,
    normalize_salesforce_organization,
    persist_salesforce_organization_name,
)


ORGANIZATION_RECORD = {
    "Id": "00D5g00000OrgIdA",
    "Name": "Acme Production",
    "TimeZoneSidKey": "America/Los_Angeles",
    "IsSandbox": False,
    "OrganizationType": "Enterprise Edition",
}

CONNECTION_ROW = {
    "ROWID": "sf-row-1",
    "salesforce_org_id": "00D5g00000Stored",
    "organization_name": "Stored Org",
}


class FakeTable:
    def __init__(self):
        self.updates = []

    def update_row(self, row):
        self.updates.append(dict(row))
        return row


class FakeDatastore:
    def __init__(self):
        self.table_obj = FakeTable()
        self.table_names = []

    def table(self, name):
        self.table_names.append(name)
        return self.table_obj


class SalesforceOrganizationNormalizationTests(unittest.TestCase):
    def test_maps_id_name_and_timezone_sid_key(self):
        organization = normalize_salesforce_organization(
            ORGANIZATION_RECORD, CONNECTION_ROW
        )
        self.assertEqual(
            organization,
            {
                "id": "00D5g00000OrgIdA",
                "name": "Acme Production",
                "timeZone": "America/Los_Angeles",
                "isSandbox": False,
                "organizationType": "Enterprise Edition",
            },
        )

    def test_exposes_timezone_sid_key_as_time_zone(self):
        organization = normalize_salesforce_organization(
            {**ORGANIZATION_RECORD, "TimeZoneSidKey": "Asia/Kolkata"},
            CONNECTION_ROW,
        )
        self.assertEqual(organization["timeZone"], "Asia/Kolkata")
        self.assertNotIn("TimeZoneSidKey", organization)

    def test_missing_timezone_does_not_crash(self):
        organization = normalize_salesforce_organization(
            {
                "Id": "00D5g00000OrgIdA",
                "Name": "Acme Production",
                "TimeZoneSidKey": "",
                "IsSandbox": True,
                "OrganizationType": "Developer Edition",
            },
            CONNECTION_ROW,
        )
        self.assertEqual(organization["id"], "00D5g00000OrgIdA")
        self.assertEqual(organization["name"], "Acme Production")
        self.assertEqual(organization["timeZone"], "")
        self.assertTrue(organization["isSandbox"])

    def test_absent_timezone_field_is_empty_string(self):
        organization = normalize_salesforce_organization(
            {"Id": "00D5g00000OrgIdA", "Name": "Acme Production"},
            CONNECTION_ROW,
        )
        self.assertEqual(organization["timeZone"], "")
        self.assertIsNone(organization["isSandbox"])


class SalesforceOrganizationFallbackTests(unittest.TestCase):
    def test_uses_stored_id_and_name_when_query_fields_are_empty(self):
        organization = normalize_salesforce_organization({}, CONNECTION_ROW)
        self.assertEqual(organization["id"], "00D5g00000Stored")
        self.assertEqual(organization["name"], "Stored Org")
        self.assertEqual(organization["timeZone"], "")
        self.assertIsNone(organization["isSandbox"])
        self.assertEqual(organization["organizationType"], "")

    def test_query_failure_falls_back_to_stored_organization(self):
        with patch(
            "salesforce.client._authorized_get",
            side_effect=requests.ConnectionError("network"),
        ), self.assertLogs("salesforce.client", level="WARNING"):
            organization = fetch_salesforce_organization(
                "stored-access-token",
                "https://example.my.salesforce.com",
                CONNECTION_ROW,
            )
        self.assertEqual(organization["id"], "00D5g00000Stored")
        self.assertEqual(organization["name"], "Stored Org")
        self.assertEqual(organization["timeZone"], "")

    def test_empty_timezone_in_query_result_still_returns_organization(self):
        with patch(
            "salesforce.client._authorized_get",
            return_value={
                "records": [
                    {
                        "Id": "00D5g00000OrgIdA",
                        "Name": "Acme Production",
                        "TimeZoneSidKey": None,
                    }
                ]
            },
        ):
            organization = fetch_salesforce_organization(
                "stored-access-token",
                "https://example.my.salesforce.com",
                CONNECTION_ROW,
            )
        self.assertEqual(organization["id"], "00D5g00000OrgIdA")
        self.assertEqual(organization["timeZone"], "")


class SalesforceOrganizationPersistTests(unittest.TestCase):
    def test_persists_discovered_organization_name_on_existing_column(self):
        row = dict(CONNECTION_ROW)
        datastore = FakeDatastore()
        persist_salesforce_organization_name(
            datastore,
            row,
            {"id": "00D5g00000OrgIdA", "name": "Acme Production"},
        )
        self.assertEqual(datastore.table_names, [SALESFORCE_CONNECTIONS_TABLE])
        self.assertEqual(
            datastore.table_obj.updates,
            [{"ROWID": "sf-row-1", "organization_name": "Acme Production"}],
        )
        self.assertEqual(row["organization_name"], "Acme Production")

    def test_does_not_write_when_name_is_unchanged(self):
        datastore = FakeDatastore()
        persist_salesforce_organization_name(
            datastore,
            dict(CONNECTION_ROW),
            {"name": "Stored Org"},
        )
        self.assertEqual(datastore.table_obj.updates, [])


class SalesforceOrganizationQueryTests(unittest.TestCase):
    def test_query_selects_timezone_and_sandbox_fields(self):
        self.assertEqual(
            SALESFORCE_ORGANIZATION_QUERY,
            "SELECT Id, Name, TimeZoneSidKey, IsSandbox, OrganizationType FROM Organization",
        )

    def test_fetch_uses_stored_access_token_not_a_client_supplied_token(self):
        with patch(
            "salesforce.client._authorized_get",
            return_value={"records": [ORGANIZATION_RECORD]},
        ) as authorized_get:
            organization = fetch_salesforce_organization(
                "stored-access-token",
                "https://example.my.salesforce.com",
                CONNECTION_ROW,
            )
        self.assertEqual(organization["timeZone"], "America/Los_Angeles")
        authorized_get.assert_called_once()
        args, kwargs = authorized_get.call_args
        self.assertIn("/services/data/v62.0/query", args[0])
        self.assertEqual(args[1], "stored-access-token")
        self.assertEqual(kwargs["params"]["q"], SALESFORCE_ORGANIZATION_QUERY)

    def test_metadata_route_still_uses_existing_token_refresh(self):
        discovery_source = (
            Path(FUNCTION_ROOT) / "salesforce" / "discovery.py"
        ).read_text(encoding="utf-8")
        self.assertIn("get_salesforce_access_token", discovery_source)
        self.assertIn("fetch_salesforce_organization", discovery_source)
        self.assertIn("timeZone", discovery_source)
        client_source = (Path(FUNCTION_ROOT) / "salesforce" / "client.py").read_text(
            encoding="utf-8"
        )
        fetch_block = client_source.split("def fetch_salesforce_organization", 1)[1]
        fetch_block = fetch_block.split("def _excluded_by_name", 1)[0]
        self.assertNotIn("get_salesforce_access_token", fetch_block)
        self.assertIn("SALESFORCE_ORGANIZATION_QUERY", fetch_block)


if __name__ == "__main__":
    unittest.main()
