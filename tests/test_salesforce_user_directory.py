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

from salesforce.user_directory import (
    SALESFORCE_DIRECTORY_TABLE,
    SALESFORCE_GROUP_QUERY,
    SALESFORCE_USER_QUERY,
    fetch_salesforce_users,
    is_salesforce_record_id,
    normalize_salesforce_group,
    normalize_salesforce_user,
    sync_salesforce_owner_directory,
    upsert_salesforce_directory_entries,
)


USER_ID = "0055g00000AbCdEFGH"
QUEUE_ID = "00G5g00000QueueABC"
GROUP_ID = "00G5g00000GroupABC"
CONNECTION_ROW_ID = "1234567890"


class FakeTable:
    def __init__(self):
        self.updates = []
        self.inserts = []
        self._next_row = 1

    def insert_row(self, row):
        stored = dict(row)
        stored.setdefault("ROWID", f"row-{self._next_row}")
        self._next_row += 1
        self.inserts.append(stored)
        return stored

    def update_row(self, row):
        self.updates.append(dict(row))
        return row


class FakeDatastore:
    def __init__(self, table=None):
        self.table_obj = table or FakeTable()
        self.table_names = []

    def table(self, name):
        self.table_names.append(name)
        return self.table_obj


class FakeZcql:
    def __init__(self, rows=None, error=None):
        self.rows = rows or []
        self.error = error
        self.queries = []

    def execute_query(self, query):
        self.queries.append(query)
        if self.error:
            raise self.error
        return [{SALESFORCE_DIRECTORY_TABLE: row} for row in self.rows]


def user_record(**overrides):
    record = {
        "Id": USER_ID,
        "Name": "Ada Lovelace",
        "Email": "ada@example.com",
        "IsActive": True,
        "Username": "ada@example.com",
    }
    record.update(overrides)
    return record


def queue_record(**overrides):
    record = {
        "Id": QUEUE_ID,
        "Name": "Sales Queue",
        "Type": "Queue",
        "Email": "sales-queue@example.com",
    }
    record.update(overrides)
    return record


class SalesforceUserNormalizationTests(unittest.TestCase):
    def test_normalizes_active_user(self):
        self.assertEqual(
            normalize_salesforce_user(user_record()),
            {
                "crmUserId": USER_ID,
                "displayName": "Ada Lovelace",
                "email": "ada@example.com",
                "username": "ada@example.com",
                "active": True,
                "type": "user",
            },
        )

    def test_normalizes_inactive_user(self):
        entry = normalize_salesforce_user(user_record(IsActive=False))
        self.assertFalse(entry["active"])
        self.assertEqual(entry["type"], "user")
        self.assertEqual(entry["crmUserId"], USER_ID)

    def test_missing_email_and_username_become_empty_strings(self):
        entry = normalize_salesforce_user(
            user_record(Email=None, Username=None, Name="No Contact")
        )
        self.assertEqual(entry["email"], "")
        self.assertEqual(entry["username"], "")
        self.assertEqual(entry["displayName"], "No Contact")

    def test_requires_salesforce_id(self):
        self.assertIsNone(normalize_salesforce_user(user_record(Id="")))
        self.assertIsNone(normalize_salesforce_user(user_record(Id="not-an-id")))


class SalesforceQueueNormalizationTests(unittest.TestCase):
    def test_normalizes_queue(self):
        self.assertEqual(
            normalize_salesforce_group(queue_record()),
            {
                "crmUserId": QUEUE_ID,
                "displayName": "Sales Queue",
                "email": "sales-queue@example.com",
                "username": "",
                "active": True,
                "type": "queue",
            },
        )

    def test_regular_group_is_not_a_queue(self):
        entry = normalize_salesforce_group(
            {"Id": GROUP_ID, "Name": "All Sales", "Type": "Regular"}
        )
        self.assertEqual(entry["type"], "group")
        self.assertEqual(entry["crmUserId"], GROUP_ID)
        self.assertNotEqual(entry["type"], "user")

    def test_user_and_queue_types_are_distinct(self):
        user = normalize_salesforce_user(user_record())
        queue = normalize_salesforce_group(queue_record())
        self.assertEqual(user["type"], "user")
        self.assertEqual(queue["type"], "queue")
        self.assertNotEqual(user["crmUserId"], queue["crmUserId"])

    def test_skips_non_owner_group_types(self):
        self.assertIsNone(
            normalize_salesforce_group(
                {"Id": GROUP_ID, "Name": "CEO Role", "Type": "Role"}
            )
        )


class SalesforceIdTests(unittest.TestCase):
    def test_accepts_eighteen_character_ids(self):
        self.assertTrue(is_salesforce_record_id(USER_ID))
        self.assertEqual(len(USER_ID), 18)
        self.assertEqual(normalize_salesforce_user(user_record())["crmUserId"], USER_ID)
        self.assertEqual(len(normalize_salesforce_group(queue_record())["crmUserId"]), 18)

    def test_does_not_invent_fifteen_to_eighteen_conversion(self):
        fifteen = "0055g00000AbCdE"
        self.assertEqual(len(fifteen), 15)
        self.assertTrue(is_salesforce_record_id(fifteen))
        entry = normalize_salesforce_user(user_record(Id=fifteen))
        self.assertEqual(entry["crmUserId"], fifteen)
        self.assertEqual(len(entry["crmUserId"]), 15)


class SalesforceDirectoryUpsertTests(unittest.TestCase):
    def test_inserts_then_updates_same_owner_without_duplicates(self):
        table = FakeTable()
        first = upsert_salesforce_directory_entries(
            table,
            [],
            [normalize_salesforce_user(user_record())],
            CONNECTION_ROW_ID,
            "2026-09-16 12:00:00",
            managed_types={"user"},
        )
        self.assertEqual(first["inserted"], 1)
        self.assertEqual(first["updated"], 0)
        existing = [dict(table.inserts[0])]
        second = upsert_salesforce_directory_entries(
            table,
            existing,
            [
                normalize_salesforce_user(
                    user_record(Name="Ada L.", Email="ada2@example.com")
                )
            ],
            CONNECTION_ROW_ID,
            "2026-09-16 13:00:00",
            managed_types={"user"},
        )
        self.assertEqual(second["inserted"], 0)
        self.assertEqual(second["updated"], 1)
        self.assertEqual(len(table.inserts), 1)
        self.assertEqual(table.updates[0]["display_name"], "Ada L.")
        self.assertEqual(table.updates[0]["crm_user_id"], USER_ID)

    def test_duplicate_payload_rows_are_not_inserted_twice(self):
        table = FakeTable()
        result = upsert_salesforce_directory_entries(
            table,
            [],
            [
                normalize_salesforce_user(user_record()),
                normalize_salesforce_user(user_record(Name="Duplicate")),
            ],
            CONNECTION_ROW_ID,
            "2026-09-16 12:00:00",
            managed_types={"user"},
        )
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(len(table.inserts), 1)

    def test_missing_users_are_marked_inactive_not_deleted(self):
        existing = {
            "ROWID": "row-1",
            "directory_key": f"{CONNECTION_ROW_ID}:{USER_ID}",
            "crm_user_id": USER_ID,
            "owner_type": "user",
            "active": True,
        }
        table = FakeTable()
        result = upsert_salesforce_directory_entries(
            table,
            [existing],
            [normalize_salesforce_group(queue_record())],
            CONNECTION_ROW_ID,
            "2026-09-16 12:00:00",
            managed_types={"user", "queue", "group"},
        )
        self.assertEqual(result["inactivated"], 1)
        self.assertEqual(table.updates[0]["ROWID"], "row-1")
        self.assertFalse(table.updates[0]["active"])
        self.assertEqual(len(table.inserts), 1)

    def test_does_not_inactivate_queues_when_only_users_were_fetched(self):
        existing_queue = {
            "ROWID": "row-q",
            "directory_key": f"{CONNECTION_ROW_ID}:{QUEUE_ID}",
            "crm_user_id": QUEUE_ID,
            "owner_type": "queue",
            "active": True,
        }
        table = FakeTable()
        upsert_salesforce_directory_entries(
            table,
            [existing_queue],
            [normalize_salesforce_user(user_record())],
            CONNECTION_ROW_ID,
            "2026-09-16 12:00:00",
            managed_types={"user"},
        )
        self.assertEqual(table.updates, [])


class SalesforceDirectorySyncTests(unittest.TestCase):
    def test_sync_uses_salesforce_table_and_stored_token(self):
        datastore = FakeDatastore()
        zcql = FakeZcql()
        with patch(
            "salesforce.user_directory.fetch_salesforce_users",
            return_value=([normalize_salesforce_user(user_record())], 1),
        ) as fetch_users, patch(
            "salesforce.user_directory.fetch_salesforce_groups",
            return_value=([normalize_salesforce_group(queue_record())], 1),
        ):
            result = sync_salesforce_owner_directory(
                datastore,
                zcql,
                {"ROWID": CONNECTION_ROW_ID},
                "stored-access-token",
                "https://example.my.salesforce.com",
            )
        fetch_users.assert_called_once_with(
            "stored-access-token", "https://example.my.salesforce.com"
        )
        self.assertEqual(datastore.table_names, [SALESFORCE_DIRECTORY_TABLE])
        self.assertNotIn("zoho_connection_users", datastore.table_names)
        self.assertTrue(result["refreshed"])
        self.assertEqual(result["counts"], {"user": 1, "queue": 1, "group": 0})
        self.assertIn(SALESFORCE_DIRECTORY_TABLE, zcql.queries[0])
        self.assertNotIn("zoho_connection_users", zcql.queries[0])

    def test_api_failure_does_not_crash_and_does_not_write_when_both_fail(self):
        datastore = FakeDatastore()
        zcql = FakeZcql()
        with patch(
            "salesforce.user_directory.fetch_salesforce_users",
            side_effect=requests.HTTPError("401"),
        ), patch(
            "salesforce.user_directory.fetch_salesforce_groups",
            side_effect=requests.ConnectionError("network"),
        ), self.assertLogs("salesforce.user_directory", level="WARNING"):
            result = sync_salesforce_owner_directory(
                datastore,
                zcql,
                {"ROWID": CONNECTION_ROW_ID},
                "stored-access-token",
                "https://example.my.salesforce.com",
            )
        self.assertFalse(result["refreshed"])
        self.assertIn("failed", result["warning"].lower())
        self.assertEqual(datastore.table_obj.inserts, [])
        self.assertEqual(datastore.table_obj.updates, [])

    def test_user_query_uses_soql_and_stored_access_token(self):
        with patch(
            "salesforce.user_directory._salesforce_authorized_get",
            return_value={"done": True, "records": [user_record()]},
        ) as authorized_get:
            entries, pages = fetch_salesforce_users(
                "stored-access-token", "https://example.my.salesforce.com"
            )
        self.assertEqual(pages, 1)
        self.assertEqual(entries[0]["crmUserId"], USER_ID)
        args, kwargs = authorized_get.call_args
        self.assertIn("/services/data/v62.0/query", args[0])
        self.assertEqual(args[1], "stored-access-token")
        self.assertEqual(kwargs["params"]["q"], SALESFORCE_USER_QUERY)

    def test_group_query_is_limited_to_queue_and_regular(self):
        self.assertIn("Type IN ('Queue', 'Regular')", SALESFORCE_GROUP_QUERY)
        self.assertIn("FROM Group", SALESFORCE_GROUP_QUERY)

    def test_source_does_not_use_zoho_directory_table(self):
        source = (
            Path(FUNCTION_ROOT) / "salesforce" / "user_directory.py"
        ).read_text(encoding="utf-8")
        self.assertIn("salesforce_connection_owners", source)
        self.assertNotIn("from zoho", source)
        implementation = source.split("SALESFORCE_DIRECTORY_TABLE", 1)[1]
        self.assertNotIn("zoho_connection_users", implementation)

    def test_route_uses_existing_token_refresh(self):
        source = (
            Path(FUNCTION_ROOT) / "salesforce" / "user_directory.py"
        ).read_text(encoding="utf-8")
        self.assertIn("get_salesforce_access_token", source)
        self.assertIn("get_salesforce_owner_directory", source)


if __name__ == "__main__":
    unittest.main()
