import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import ANY, Mock, patch

import requests


FUNCTION_ROOT = (
    Path(__file__).resolve().parents[1]
    / "functions"
    / "ai_data_analytics_function"
)
sys.path.insert(0, str(FUNCTION_ROOT))

from salesforce.bulk_query import (
    SALESFORCE_QUERY_CLOCK_FIELDS,
    SalesforceBulkError,
    build_salesforce_query_soql,
    build_salesforce_query_soql_from_plan,
    persist_salesforce_query_job,
    poll_salesforce_query_job,
    salesforce_query_jobs_url,
    submit_salesforce_query_job,
    to_salesforce_soql_datetime,
)
from salesforce.client import SALESFORCE_API_VERSION


INSTANCE = "https://example.my.salesforce.com"
JOB_ID = "7505g00000AbCdEAAX"
CONNECTION = {
    "ROWID": "sf-row-1",
    "access_token": "stored-access-token",
    "refresh_token": "stored-refresh-token",
    "instance_url": INSTANCE,
}
ACCOUNT_FIELDS = ["Id", "Name", "CreatedDate", "LastModifiedDate"]
OPPORTUNITY_FIELDS = [
    "Id",
    "Name",
    "StageName",
    "CreatedDate",
    "LastModifiedDate",
]
FROM_UTC = datetime(2026, 9, 9, 12, 0, 0, tzinfo=timezone.utc)
TO_UTC = datetime(2026, 9, 16, 12, 0, 0, tzinfo=timezone.utc)


def json_response(payload, status=200):
    response = Mock()
    response.ok = 200 <= status < 300
    response.status_code = status
    response.json.return_value = payload
    if status >= 400:
        http_error = requests.HTTPError(response=response)
        response.raise_for_status.side_effect = http_error
    else:
        response.raise_for_status.return_value = None
    return response


class FakeTable:
    def __init__(self):
        self.inserts = []
        self.updates = []
        self._next = 1

    def insert_row(self, row):
        stored = dict(row)
        stored.setdefault("ROWID", str(self._next))
        self._next += 1
        self.inserts.append(stored)
        return stored

    def update_row(self, row):
        stored = dict(row)
        self.updates.append(stored)
        return stored


class FakeDatastore:
    def __init__(self):
        self.tables = {}
        self.table_names = []

    def table(self, name):
        self.table_names.append(name)
        if name not in self.tables:
            self.tables[name] = FakeTable()
        return self.tables[name]


class SalesforceSoqlBuilderTests(unittest.TestCase):
    def test_account_soql_uses_salesforce_api_name(self):
        soql = build_salesforce_query_soql(
            "Account", ACCOUNT_FIELDS, "CreatedDate", FROM_UTC, TO_UTC
        )
        self.assertIn("FROM Account", soql)
        self.assertNotIn("Accounts", soql)
        self.assertTrue(soql.startswith("SELECT "))
        self.assertIn("Id", soql)
        self.assertIn("Name", soql)

    def test_opportunity_soql_uses_salesforce_api_name(self):
        soql = build_salesforce_query_soql(
            "Opportunity",
            OPPORTUNITY_FIELDS,
            "LastModifiedDate",
            FROM_UTC,
            TO_UTC,
        )
        self.assertIn("FROM Opportunity", soql)
        self.assertNotIn("Deals", soql)
        self.assertIn("StageName", soql)

    def test_created_date_filter(self):
        soql = build_salesforce_query_soql(
            "Account", ACCOUNT_FIELDS, "CreatedDate", FROM_UTC, TO_UTC
        )
        self.assertIn("CreatedDate >= 2026-09-09T12:00:00Z", soql)
        self.assertIn("CreatedDate < 2026-09-16T12:00:00Z", soql)
        self.assertNotIn("Created_Time", soql)

    def test_last_modified_date_filter(self):
        soql = build_salesforce_query_soql(
            "Account", ACCOUNT_FIELDS, "LastModifiedDate", FROM_UTC, TO_UTC
        )
        self.assertIn("LastModifiedDate >= 2026-09-09T12:00:00Z", soql)
        self.assertIn("LastModifiedDate < 2026-09-16T12:00:00Z", soql)
        self.assertNotIn("Modified_Time", soql)

    def test_utc_datetime_formatting_is_not_zoho(self):
        self.assertEqual(
            to_salesforce_soql_datetime(FROM_UTC), "2026-09-09T12:00:00Z"
        )
        self.assertEqual(
            to_salesforce_soql_datetime("2026-09-16 12:00:00"),
            "2026-09-16T12:00:00Z",
        )
        formatted = to_salesforce_soql_datetime(TO_UTC)
        self.assertTrue(formatted.endswith("Z"))
        self.assertNotIn("+00:00", formatted)
        self.assertEqual(SALESFORCE_QUERY_CLOCK_FIELDS, {"CreatedDate", "LastModifiedDate"})

    def test_open_ended_range_keeps_upper_bound_only(self):
        soql = build_salesforce_query_soql(
            "Account", ACCOUNT_FIELDS, "CreatedDate", None, TO_UTC
        )
        self.assertNotIn(">=", soql)
        self.assertIn("CreatedDate < 2026-09-16T12:00:00Z", soql)

    def test_plan_builder_reads_allowlist_and_clock(self):
        soql = build_salesforce_query_soql_from_plan(
            {
                "clock_field": "CreatedDate",
                "from_utc": "2026-09-09 12:00:00",
                "to_utc": "2026-09-16 12:00:00",
            },
            {
                "module_api_name": "Contact",
                "field_allowlist_json": json.dumps(ACCOUNT_FIELDS),
            },
        )
        self.assertIn("FROM Contact", soql)
        self.assertIn("CreatedDate >= 2026-09-09T12:00:00Z", soql)

    def test_rejects_invalid_object_identifier(self):
        with self.assertRaises(SalesforceBulkError) as raised:
            build_salesforce_query_soql(
                "Account WHERE Id='001'",
                ACCOUNT_FIELDS,
                "CreatedDate",
                FROM_UTC,
                TO_UTC,
            )
        self.assertEqual(raised.exception.code, "INVALID_OBJECT_API_NAME")
        with self.assertRaises(SalesforceBulkError):
            build_salesforce_query_soql(
                "Account;DROP", ACCOUNT_FIELDS, "CreatedDate", FROM_UTC, TO_UTC
            )

    def test_rejects_invalid_field_identifier(self):
        with self.assertRaises(SalesforceBulkError) as raised:
            build_salesforce_query_soql(
                "Account",
                ["Id", "Name;SELECT", "CreatedDate"],
                "CreatedDate",
                FROM_UTC,
                TO_UTC,
            )
        self.assertEqual(raised.exception.code, "INVALID_FIELD_API_NAME")
        with self.assertRaises(SalesforceBulkError):
            build_salesforce_query_soql(
                "Account",
                ["Id", "Account.Name", "CreatedDate"],
                "CreatedDate",
                FROM_UTC,
                TO_UTC,
            )

    def test_does_not_accept_raw_soql_as_object_or_field(self):
        with self.assertRaises(SalesforceBulkError):
            build_salesforce_query_soql(
                "SELECT Id FROM Account",
                ACCOUNT_FIELDS,
                "CreatedDate",
                FROM_UTC,
                TO_UTC,
            )


class SalesforceBulkSubmitTests(unittest.TestCase):
    def test_successful_submit_posts_query_job(self):
        datastore = FakeDatastore()
        captured = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            captured["timeout"] = timeout
            return json_response(
                {
                    "id": JOB_ID,
                    "operation": "query",
                    "object": "Account",
                    "state": "UploadComplete",
                    "jobType": "V2Query",
                }
            )

        with patch(
            "salesforce.client.get_salesforce_access_token",
            return_value=("refreshed-access-token", INSTANCE),
        ) as token_fn, patch("salesforce.bulk_query.requests.post", side_effect=fake_post):
            job = submit_salesforce_query_job(
                datastore,
                CONNECTION,
                "Account",
                ACCOUNT_FIELDS,
                "CreatedDate",
                FROM_UTC,
                TO_UTC,
            )
        self.assertEqual(job["id"], JOB_ID)
        self.assertEqual(job["state"], "UploadComplete")
        self.assertEqual(job["internalStatus"], "SUBMITTED")
        self.assertEqual(
            captured["url"],
            f"{INSTANCE}/services/data/{SALESFORCE_API_VERSION}/jobs/query",
        )
        self.assertEqual(captured["headers"]["Content-Type"], "application/json")
        self.assertEqual(
            captured["headers"]["Authorization"], "Bearer refreshed-access-token"
        )
        self.assertEqual(captured["json"]["operation"], "query")
        self.assertIn("FROM Account", captured["json"]["query"])
        self.assertIn("CreatedDate >= 2026-09-09T12:00:00Z", captured["json"]["query"])
        token_fn.assert_called_once_with(datastore, CONNECTION)

    def test_job_id_is_persisted_as_provider_job_id(self):
        datastore = FakeDatastore()
        with patch(
            "salesforce.client.get_salesforce_access_token",
            return_value=("stored-access-token", INSTANCE),
        ), patch(
            "salesforce.bulk_query.requests.post",
            return_value=json_response(
                {"id": JOB_ID, "operation": "query", "state": "UploadComplete"}
            ),
        ):
            submit_salesforce_query_job(
                datastore,
                CONNECTION,
                "Account",
                ACCOUNT_FIELDS,
                "CreatedDate",
                FROM_UTC,
                TO_UTC,
                bulk_row={"scan_module_row_id": "99"},
            )
        inserted = datastore.tables["bulk_read_jobs"].inserts[0]
        self.assertEqual(inserted["provider_job_id"], JOB_ID)
        self.assertEqual(inserted["status"], "SUBMITTED")
        self.assertNotIn("zoho_job_id", inserted)
        self.assertTrue(str(inserted["bulk_job_id"]).startswith("bulk_"))

    def test_persist_updates_existing_row_without_zoho_job_id(self):
        datastore = FakeDatastore()
        persist_salesforce_query_job(
            datastore,
            {"id": JOB_ID, "internalStatus": "SUBMITTED", "state": "UploadComplete"},
            bulk_row={"ROWID": "17"},
        )
        updated = datastore.tables["bulk_read_jobs"].updates[0]
        self.assertEqual(updated["ROWID"], "17")
        self.assertEqual(updated["provider_job_id"], JOB_ID)
        self.assertNotIn("zoho_job_id", updated)

    def test_submit_uses_stored_token_refresh(self):
        datastore = FakeDatastore()
        with patch(
            "salesforce.client.get_salesforce_access_token",
            return_value=("rotated-access-token", INSTANCE),
        ) as token_fn, patch(
            "salesforce.bulk_query.requests.post",
            return_value=json_response(
                {"id": JOB_ID, "operation": "query", "state": "UploadComplete"}
            ),
        ) as post_fn:
            submit_salesforce_query_job(
                datastore,
                CONNECTION,
                "Opportunity",
                OPPORTUNITY_FIELDS,
                "LastModifiedDate",
                FROM_UTC,
                TO_UTC,
            )
        token_fn.assert_called_once_with(datastore, CONNECTION)
        headers = post_fn.call_args.kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Bearer rotated-access-token")
        self.assertNotIn("stored-access-token", headers["Authorization"])

    def test_salesforce_api_error_does_not_expose_token(self):
        with patch(
            "salesforce.client.get_salesforce_access_token",
            return_value=("secret-access-token", INSTANCE),
        ), patch(
            "salesforce.bulk_query.requests.post",
            return_value=json_response(
                [{"message": "No such column", "errorCode": "INVALID_FIELD"}],
                status=400,
            ),
        ):
            with self.assertRaises(SalesforceBulkError) as raised:
                submit_salesforce_query_job(
                    datastore=FakeDatastore(),
                    connection_row=CONNECTION,
                    object_api_name="Account",
                    field_names=ACCOUNT_FIELDS,
                    clock_field="CreatedDate",
                    from_utc=FROM_UTC,
                    to_utc=TO_UTC,
                )
        self.assertEqual(raised.exception.code, "INVALID_FIELD_API_NAME")
        self.assertNotIn("secret-access-token", str(raised.exception))
        self.assertNotIn("secret-access-token", raised.exception.code)

    def test_malformed_query_maps_to_invalid_soql(self):
        with patch(
            "salesforce.client.get_salesforce_access_token",
            return_value=("stored-access-token", INSTANCE),
        ), patch(
            "salesforce.bulk_query.requests.post",
            return_value=json_response(
                [{"message": "unexpected token", "errorCode": "MALFORMED_QUERY"}],
                status=400,
            ),
        ):
            with self.assertRaises(SalesforceBulkError) as raised:
                submit_salesforce_query_job(
                    FakeDatastore(),
                    CONNECTION,
                    "Account",
                    ACCOUNT_FIELDS,
                    "CreatedDate",
                    FROM_UTC,
                    TO_UTC,
                )
        self.assertEqual(raised.exception.code, "INVALID_SOQL")


class SalesforceBulkStatusTests(unittest.TestCase):
    def _poll(self, payload, status=200, job_id=JOB_ID, bulk_row=None):
        datastore = FakeDatastore()
        with patch(
            "salesforce.client.get_salesforce_access_token",
            return_value=("stored-access-token", INSTANCE),
        ) as token_fn, patch(
            "salesforce.bulk_query.requests.get",
            return_value=json_response(payload, status=status),
        ) as get_fn:
            job = poll_salesforce_query_job(
                datastore, CONNECTION, job_id, bulk_row=bulk_row
            )
        return job, datastore, token_fn, get_fn

    def test_upload_complete_and_in_progress(self):
        upload, _, _, _ = self._poll(
            {"id": JOB_ID, "state": "UploadComplete", "operation": "query"}
        )
        self.assertEqual(upload["internalStatus"], "SUBMITTED")
        self.assertFalse(upload["resultsAvailable"])
        in_progress, _, token_fn, get_fn = self._poll(
            {"id": JOB_ID, "state": "InProgress", "operation": "query"}
        )
        self.assertEqual(in_progress["internalStatus"], "PROCESSING")
        token_fn.assert_called_once_with(ANY, CONNECTION)
        called_url = get_fn.call_args.kwargs.get("url") or get_fn.call_args.args[0]
        self.assertIn(
            f"/services/data/{SALESFORCE_API_VERSION}/jobs/query/{JOB_ID}",
            called_url,
        )

    def test_job_complete_exposes_counts_without_downloading(self):
        job, datastore, _, get_fn = self._poll(
            {
                "id": JOB_ID,
                "state": "JobComplete",
                "operation": "query",
                "object": "Account",
                "numberRecordsProcessed": "42",
                "numberRecordsFailed": 0,
                "locator": "batch-locator-1",
            },
            bulk_row={"ROWID": "21"},
        )
        self.assertEqual(job["internalStatus"], "READY_TO_DOWNLOAD")
        self.assertTrue(job["resultsAvailable"])
        self.assertEqual(job["numberRecordsProcessed"], 42)
        self.assertEqual(job["numberRecordsFailed"], 0)
        self.assertEqual(job["locator"], "batch-locator-1")
        self.assertTrue(job["locatorAvailable"])
        updated = datastore.tables["bulk_read_jobs"].updates[0]
        self.assertEqual(updated["provider_job_id"], JOB_ID)
        self.assertEqual(updated["provider_record_count"], 42)
        self.assertEqual(updated["status"], "READY_TO_DOWNLOAD")
        self.assertNotIn("zoho_job_id", updated)
        called_url = get_fn.call_args.kwargs.get("url") or get_fn.call_args.args[0]
        self.assertNotIn("/results", called_url)

    def test_failed_status(self):
        job, _, _, _ = self._poll({"id": JOB_ID, "state": "Failed"})
        self.assertEqual(job["state"], "Failed")
        self.assertEqual(job["internalStatus"], "FAILED_TERMINAL")
        self.assertFalse(job["resultsAvailable"])

    def test_aborted_status(self):
        job, _, _, _ = self._poll({"id": JOB_ID, "state": "Aborted"})
        self.assertEqual(job["state"], "Aborted")
        self.assertEqual(job["internalStatus"], "FAILED_TERMINAL")

    def test_number_records_processed_handles_missing(self):
        job, _, _, _ = self._poll(
            {"id": JOB_ID, "state": "InProgress", "numberRecordsProcessed": ""}
        )
        self.assertIsNone(job["numberRecordsProcessed"])

    def test_status_http_error(self):
        with patch(
            "salesforce.client.get_salesforce_access_token",
            return_value=("stored-access-token", INSTANCE),
        ), patch(
            "salesforce.bulk_query.requests.get",
            return_value=json_response(
                [{"message": "Invalid job", "errorCode": "INVALID_JOB"}],
                status=404,
            ),
        ):
            with self.assertRaises(SalesforceBulkError) as raised:
                poll_salesforce_query_job(FakeDatastore(), CONNECTION, JOB_ID)
        self.assertEqual(raised.exception.code, "SALESFORCE_BULK_QUERY_FAILED")

    def test_invalid_job_id_is_rejected_before_http(self):
        with self.assertRaises(SalesforceBulkError) as raised:
            salesforce_query_jobs_url(INSTANCE, "../other")
        self.assertEqual(raised.exception.code, "INVALID_JOB_ID")

    def test_malformed_status_payload(self):
        with patch(
            "salesforce.client.get_salesforce_access_token",
            return_value=("stored-access-token", INSTANCE),
        ), patch(
            "salesforce.bulk_query.requests.get",
            return_value=json_response(["not-a-job"]),
        ):
            with self.assertRaises(SalesforceBulkError) as raised:
                poll_salesforce_query_job(FakeDatastore(), CONNECTION, JOB_ID)
        self.assertEqual(raised.exception.code, "SALESFORCE_JOB_RESPONSE_INVALID")


class SalesforceBulkIsolationTests(unittest.TestCase):
    def test_module_does_not_use_zoho_bulk_read(self):
        source = (Path(FUNCTION_ROOT) / "salesforce" / "bulk_query.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("from bulk_read import", source)
        self.assertNotIn("from zoho", source)
        self.assertNotIn("to_zoho_datetime", source)
        self.assertNotIn('"zoho_job_id"', source)
        self.assertNotIn("'zoho_job_id'", source)
        self.assertIn("provider_job_id", source)
        self.assertIn("/jobs/query", source)
        self.assertNotIn("/results", source)

    def test_submit_signature_does_not_accept_client_tokens(self):
        import inspect

        parameters = inspect.signature(submit_salesforce_query_job).parameters
        self.assertNotIn("access_token", parameters)
        self.assertNotIn("refresh_token", parameters)
        self.assertNotIn("query", parameters)
        self.assertNotIn("soql", parameters)


if __name__ == "__main__":
    unittest.main()
