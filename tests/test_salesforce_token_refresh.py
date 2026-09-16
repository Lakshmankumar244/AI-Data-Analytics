import logging
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import requests


FUNCTION_ROOT = (
    Path(__file__).resolve().parents[1]
    / "functions"
    / "ai_data_analytics_function"
)
sys.path.insert(0, str(FUNCTION_ROOT))

from salesforce.client import (
    DEFAULT_ACCESS_TOKEN_SECONDS,
    SALESFORCE_CONNECTIONS_TABLE,
    build_salesforce_token_update,
    persist_salesforce_token_refresh,
)


NOW = datetime(2026, 9, 16, 12, 0, 0, tzinfo=timezone.utc)
STORED_INSTANCE = "https://example.my.salesforce.com"
NEW_INSTANCE = "https://rotated.my.salesforce.com"


def connection_row(**overrides):
    row = {
        "ROWID": "sf-row-1",
        "access_token": "old-access-token",
        "refresh_token": "old-refresh-token",
        "instance_url": STORED_INSTANCE,
        "token_expires_at": "2026-09-16 11:00:00:000",
    }
    row.update(overrides)
    return row


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


class SalesforceRefreshTokenRotationTests(unittest.TestCase):
    def test_persists_new_refresh_token_when_salesforce_rotates(self):
        row = connection_row()
        update = build_salesforce_token_update(
            row,
            {
                "access_token": "new-access-token",
                "refresh_token": "rotated-refresh-token",
                "instance_url": NEW_INSTANCE,
                "expires_in": 3600,
            },
            now=NOW,
        )
        self.assertEqual(update["refresh_token"], "rotated-refresh-token")
        self.assertEqual(update["access_token"], "new-access-token")
        self.assertNotEqual(update["refresh_token"], row["refresh_token"])

        datastore = FakeDatastore()
        persist_salesforce_token_refresh(
            datastore,
            row,
            {
                "access_token": "new-access-token",
                "refresh_token": "rotated-refresh-token",
                "instance_url": NEW_INSTANCE,
                "expires_in": 3600,
            },
            now=NOW,
        )
        self.assertEqual(datastore.table_names, [SALESFORCE_CONNECTIONS_TABLE])
        self.assertEqual(len(datastore.table_obj.updates), 1)
        self.assertEqual(
            datastore.table_obj.updates[0]["refresh_token"], "rotated-refresh-token"
        )
        self.assertEqual(row["refresh_token"], "rotated-refresh-token")

    def test_omits_refresh_token_column_when_salesforce_does_not_rotate(self):
        row = connection_row()
        update = build_salesforce_token_update(
            row,
            {
                "access_token": "new-access-token",
                "instance_url": NEW_INSTANCE,
                "expires_in": 7200,
            },
            now=NOW,
        )
        self.assertNotIn("refresh_token", update)
        self.assertEqual(update["access_token"], "new-access-token")

        datastore = FakeDatastore()
        persist_salesforce_token_refresh(
            datastore,
            row,
            {
                "access_token": "new-access-token",
                "expires_in": 7200,
            },
            now=NOW,
        )
        self.assertNotIn("refresh_token", datastore.table_obj.updates[0])
        self.assertEqual(row["refresh_token"], "old-refresh-token")

    def test_blank_refresh_token_is_treated_as_absent(self):
        update = build_salesforce_token_update(
            connection_row(),
            {
                "access_token": "new-access-token",
                "refresh_token": "   ",
                "expires_in": 3600,
            },
            now=NOW,
        )
        self.assertNotIn("refresh_token", update)


class SalesforceRefreshPersistenceTests(unittest.TestCase):
    def test_persists_access_token_expiry_and_instance_url(self):
        row = connection_row()
        update = build_salesforce_token_update(
            row,
            {
                "access_token": "new-access-token",
                "instance_url": NEW_INSTANCE,
                "expires_in": 3600,
            },
            now=NOW,
        )
        self.assertEqual(
            update,
            {
                "ROWID": "sf-row-1",
                "access_token": "new-access-token",
                "token_expires_at": "2026-09-16 13:00:00:000",
                "instance_url": NEW_INSTANCE,
            },
        )

    def test_keeps_stored_instance_url_when_refresh_omits_it(self):
        update = build_salesforce_token_update(
            connection_row(),
            {"access_token": "new-access-token", "expires_in": 1800},
            now=NOW,
        )
        self.assertEqual(update["instance_url"], STORED_INSTANCE)
        self.assertEqual(update["token_expires_at"], "2026-09-16 12:30:00:000")

    def test_uses_default_expiry_when_expires_in_is_omitted(self):
        update = build_salesforce_token_update(
            connection_row(),
            {"access_token": "new-access-token"},
            now=NOW,
        )
        self.assertEqual(DEFAULT_ACCESS_TOKEN_SECONDS, 7200)
        self.assertEqual(update["token_expires_at"], "2026-09-16 14:00:00:000")


class SalesforceRefreshFailureTests(unittest.TestCase):
    def test_error_payload_does_not_overwrite_refresh_token(self):
        row = connection_row()
        datastore = FakeDatastore()
        with self.assertRaises(ValueError):
            persist_salesforce_token_refresh(
                datastore,
                row,
                {
                    "error": "invalid_grant",
                    "error_description": "expired access/refresh token",
                },
                now=NOW,
            )
        self.assertEqual(datastore.table_obj.updates, [])
        self.assertEqual(datastore.table_names, [])
        self.assertEqual(row["refresh_token"], "old-refresh-token")
        self.assertEqual(row["access_token"], "old-access-token")
        self.assertEqual(row["instance_url"], STORED_INSTANCE)

    def test_missing_access_token_does_not_persist(self):
        row = connection_row()
        datastore = FakeDatastore()
        with self.assertRaises(ValueError):
            persist_salesforce_token_refresh(
                datastore,
                row,
                {"refresh_token": "should-not-be-saved", "expires_in": 3600},
                now=NOW,
            )
        self.assertEqual(datastore.table_obj.updates, [])
        self.assertEqual(row["refresh_token"], "old-refresh-token")

    def test_http_failure_does_not_call_persist(self):
        from salesforce.client import get_salesforce_access_token

        row = connection_row(token_expires_at="2026-09-16 00:00:00:000")
        datastore = FakeDatastore()
        response = Mock()
        response.raise_for_status.side_effect = requests.HTTPError("400")
        with patch.dict(
            "os.environ",
            {
                "SALESFORCE_LOGIN_URL": "https://login.salesforce.com",
                "SALESFORCE_CLIENT_ID": "client-id",
                "SALESFORCE_CLIENT_SECRET": "client-secret",
            },
        ), patch("salesforce.client.requests.post", return_value=response), patch(
            "salesforce.client.persist_salesforce_token_refresh"
        ) as persist, patch(
            "salesforce.client._discovery_error",
            side_effect=RuntimeError("TOKEN_REFRESH_FAILED"),
        ), self.assertLogs("salesforce.client", level="WARNING"):
            with self.assertRaises(RuntimeError):
                get_salesforce_access_token(datastore, row)
        persist.assert_not_called()
        self.assertEqual(datastore.table_obj.updates, [])
        self.assertEqual(row["refresh_token"], "old-refresh-token")


class SalesforceRefreshLoggingTests(unittest.TestCase):
    def test_refresh_warnings_do_not_log_tokens(self):
        from salesforce.client import get_salesforce_access_token

        row = connection_row(token_expires_at="2026-09-16 00:00:00:000")
        datastore = FakeDatastore()
        records = []

        class TokenHandler(logging.Handler):
            def emit(self, record):
                records.append(self.format(record))

        logger = logging.getLogger("salesforce.client")
        handler = TokenHandler()
        logger.addHandler(handler)
        previous_level = logger.level
        logger.setLevel(logging.WARNING)
        try:
            with patch.dict(
                "os.environ",
                {
                    "SALESFORCE_LOGIN_URL": "https://login.salesforce.com",
                    "SALESFORCE_CLIENT_ID": "client-id",
                    "SALESFORCE_CLIENT_SECRET": "client-secret",
                },
            ), patch(
                "salesforce.client.requests.post",
                side_effect=requests.ConnectionError("network"),
            ), patch(
                "salesforce.client._discovery_error",
                side_effect=RuntimeError("TOKEN_REFRESH_FAILED"),
            ):
                with self.assertRaises(RuntimeError):
                    get_salesforce_access_token(datastore, row)
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous_level)

        joined = "\n".join(records)
        self.assertNotIn("old-refresh-token", joined)
        self.assertNotIn("old-access-token", joined)
        self.assertNotIn("client-secret", joined)


if __name__ == "__main__":
    unittest.main()
