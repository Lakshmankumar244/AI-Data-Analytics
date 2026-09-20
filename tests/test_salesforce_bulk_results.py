import hashlib
import io
import logging
import sys
import unittest
from pathlib import Path
from unittest.mock import ANY, Mock, patch

import requests


FUNCTION_ROOT = (
    Path(__file__).resolve().parents[1]
    / "functions"
    / "ai_data_analytics_function"
)
sys.path.insert(0, str(FUNCTION_ROOT))

from salesforce.bulk_query import SalesforceBulkError
from salesforce.bulk_results import (
    combine_salesforce_csv_pages,
    download_salesforce_query_results,
    next_salesforce_locator,
    persist_salesforce_csv_artifact,
    salesforce_query_results_url,
    validate_salesforce_result_download,
)
from salesforce.client import SALESFORCE_API_VERSION


INSTANCE = "https://example.my.salesforce.com"
JOB_ID = "7505g00000AbCdEAAX"
HEADER = "Id,Name,CreatedDate"
PAGE_ONE = f"{HEADER}\n001A,Acme,2026-09-10T00:00:00.000Z\n".encode("utf-8")
PAGE_TWO = f"{HEADER}\n001B,Beta,2026-09-11T00:00:00.000Z\n".encode("utf-8")
EMPTY_PAGE = f"{HEADER}\n".encode("utf-8")
CONNECTION = {
    "ROWID": "555",
    "user_id": "user-1",
    "access_token": "stored-access-token",
    "refresh_token": "stored-refresh-token",
    "instance_url": INSTANCE,
    "status": "connected",
}
SCAN = {
    "scan_id": "scan_abc",
    "crm_provider": "salesforce",
    "connection_row_id": "555",
}
BULK_ROW = {
    "ROWID": "21",
    "bulk_job_id": "bulk_abc",
    "provider_job_id": JOB_ID,
    "status": "READY_TO_DOWNLOAD",
}


class FakeTable:
    def __init__(self):
        self.updates = []

    def update_row(self, row):
        stored = dict(row)
        self.updates.append(stored)
        return stored


class FakeDatastore:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        if name not in self.tables:
            self.tables[name] = FakeTable()
        return self.tables[name]


class CatalystFilestoreError(Exception):
    """Mirrors zcatalyst_sdk.exceptions.CatalystFilestoreError."""

    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


class FakeFolder:
    def __init__(self, file_id="888"):
        self.file_id = file_id
        self.uploads = []
        self.fail = False
        self.received_types = []

    def upload_file(self, name, file_obj):
        if self.fail:
            raise RuntimeError("filestore unavailable")
        if not isinstance(file_obj, io.BufferedReader):
            raise CatalystFilestoreError(
                "INVALID_FILE_DETAILS",
                "Code must be an instance of BufferReader and cannot be empty",
            )
        self.received_types.append(type(file_obj))
        data = file_obj.read()
        self.uploads.append((name, data))
        return {"id": self.file_id}


def csv_response(content, locator=None, status=200, content_type="text/csv"):
    response = Mock()
    response.ok = 200 <= status < 300
    response.status_code = status
    response.content = content
    headers = {"Content-Type": content_type}
    if locator is not None:
        headers["Sforce-Locator"] = locator
    response.headers = headers
    if status >= 400:
        payload = content if not isinstance(content, (bytes, bytearray)) else None
        response.json.return_value = payload or [
            {"message": "Invalid job", "errorCode": "INVALID_JOB"}
        ]
        response.content = b"" if isinstance(content, list) else content
    else:
        response.json.side_effect = ValueError("not json")
    return response


class SalesforceCsvCombineTests(unittest.TestCase):
    def test_first_result_page(self):
        combined = combine_salesforce_csv_pages([PAGE_ONE])
        text = combined.decode("utf-8")
        self.assertTrue(text.startswith(HEADER))
        self.assertIn("001A,Acme", text)
        self.assertEqual(text.count(HEADER), 1)

    def test_multiple_locator_pages_keep_one_header(self):
        combined = combine_salesforce_csv_pages([PAGE_ONE, PAGE_TWO])
        text = combined.decode("utf-8")
        self.assertEqual(text.count(HEADER + "\n"), 1)
        self.assertIn("001A,Acme", text)
        self.assertIn("001B,Beta", text)
        self.assertTrue(text.startswith(HEADER + "\n"))

    def test_empty_result_keeps_header_only(self):
        combined = combine_salesforce_csv_pages([EMPTY_PAGE])
        self.assertEqual(combined, f"{HEADER}\n".encode("utf-8"))

    def test_locator_null_means_stop(self):
        self.assertIsNone(next_salesforce_locator({"Sforce-Locator": "null"}))
        self.assertIsNone(next_salesforce_locator({"Sforce-Locator": "NULL"}))
        self.assertIsNone(next_salesforce_locator({}))
        self.assertEqual(
            next_salesforce_locator({"Sforce-Locator": "next-page-token"}),
            "next-page-token",
        )

    def test_mismatched_header_is_malformed(self):
        with self.assertRaises(SalesforceBulkError) as raised:
            combine_salesforce_csv_pages(
                [PAGE_ONE, b"Id,Website\n001C,https://example.com\n"]
            )
        self.assertEqual(raised.exception.code, "MALFORMED_CSV")


class SalesforceResultDownloadTests(unittest.TestCase):
    def test_provider_job_id_is_used_never_zoho_job_id(self):
        source = (Path(FUNCTION_ROOT) / "salesforce" / "bulk_results.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("provider_job_id", source)
        self.assertNotIn('"zoho_job_id"', source)
        self.assertNotIn("'zoho_job_id'", source)
        self.assertNotIn("from bulk_read import", source)
        self.assertNotIn(".zip", source)
        with self.assertRaises(SalesforceBulkError) as raised:
            validate_salesforce_result_download(
                SCAN,
                {"status": "READY_TO_DOWNLOAD", "zoho_job_id": "111"},
                CONNECTION,
                user_id="user-1",
            )
        self.assertEqual(raised.exception.code, "PROVIDER_JOB_ID_MISSING")

    def test_wrong_provider_rejected(self):
        with self.assertRaises(SalesforceBulkError) as raised:
            validate_salesforce_result_download(
                {"crm_provider": "zoho", "connection_row_id": "555"},
                BULK_ROW,
                CONNECTION,
                user_id="user-1",
            )
        self.assertEqual(raised.exception.code, "WRONG_CRM_PROVIDER")

    def test_non_ready_job_rejected(self):
        with self.assertRaises(SalesforceBulkError) as raised:
            validate_salesforce_result_download(
                SCAN,
                {**BULK_ROW, "status": "SUBMITTED"},
                CONNECTION,
                user_id="user-1",
            )
        self.assertEqual(raised.exception.code, "BULK_JOB_STATE_CONFLICT")

    def test_other_user_is_rejected(self):
        with self.assertRaises(SalesforceBulkError) as raised:
            validate_salesforce_result_download(
                SCAN, BULK_ROW, CONNECTION, user_id="user-2"
            )
        self.assertEqual(raised.exception.code, "SCAN_NOT_OWNED")

    def _download(self, responses, folder=None, bulk_row=None, connection=None):
        datastore = FakeDatastore()
        folder = folder or FakeFolder()
        with patch(
            "salesforce.client.get_salesforce_access_token",
            return_value=("rotated-access-token", INSTANCE),
        ) as token_fn, patch(
            "salesforce.bulk_results.requests.get",
            side_effect=responses,
        ) as get_fn:
            result = download_salesforce_query_results(
                datastore,
                connection or CONNECTION,
                SCAN,
                bulk_row or dict(BULK_ROW),
                user_id="user-1",
                folder=folder,
            )
        return result, datastore, folder, token_fn, get_fn

    def test_first_page_download_persists_csv(self):
        result, datastore, folder, token_fn, get_fn = self._download(
            [csv_response(PAGE_ONE, locator="null")]
        )
        self.assertEqual(result["status"], "DOWNLOADED")
        self.assertEqual(result["providerJobId"], JOB_ID)
        self.assertEqual(result["pageCount"], 1)
        self.assertEqual(folder.uploads[0][0], f"bulk_abc_{JOB_ID}.csv")
        self.assertEqual(folder.uploads[0][1].count(HEADER.encode()), 1)
        updated = [
            row
            for row in datastore.tables["bulk_read_jobs"].updates
            if row.get("status") == "DOWNLOADED"
        ][0]
        self.assertEqual(updated["source_file_id"], "888")
        self.assertEqual(updated["source_file_name"], f"bulk_abc_{JOB_ID}.csv")
        self.assertEqual(updated["source_file_size"], len(folder.uploads[0][1]))
        self.assertEqual(
            updated["source_file_checksum"],
            hashlib.sha256(folder.uploads[0][1]).hexdigest(),
        )
        self.assertEqual(updated["status"], "DOWNLOADED")
        self.assertNotIn("zoho_job_id", updated)
        token_fn.assert_called_once()
        called_url = get_fn.call_args.args[0]
        self.assertIn(
            f"/services/data/{SALESFORCE_API_VERSION}/jobs/query/{JOB_ID}/results",
            called_url,
        )
        self.assertNotIn("zoho", called_url)

    def test_multiple_locator_pages_are_fetched(self):
        result, datastore, folder, _, get_fn = self._download(
            [
                csv_response(PAGE_ONE, locator="page-2"),
                csv_response(PAGE_TWO, locator="null"),
            ]
        )
        self.assertEqual(get_fn.call_count, 2)
        self.assertEqual(result["pageCount"], 2)
        combined = folder.uploads[0][1].decode("utf-8")
        self.assertEqual(combined.count(HEADER + "\n"), 1)
        self.assertIn("001A,Acme", combined)
        self.assertIn("001B,Beta", combined)
        second_url = get_fn.call_args_list[1].args[0]
        self.assertIn("locator=page-2", second_url)
        self.assertEqual(
            [
                row["downloaded_record_count"]
                for row in datastore.tables["bulk_read_jobs"].updates
                if "downloaded_record_count" in row
            ][-1],
            2,
        )

    def test_locator_termination_does_not_request_further_pages(self):
        _, _, _, _, get_fn = self._download(
            [csv_response(EMPTY_PAGE, locator="null")]
        )
        self.assertEqual(get_fn.call_count, 1)

    def test_empty_result_is_stored(self):
        result, _, folder, _, _ = self._download(
            [csv_response(EMPTY_PAGE, locator=None)]
        )
        self.assertEqual(result["downloadedRecordCount"], 0)
        self.assertEqual(folder.uploads[0][1], EMPTY_PAGE)

    def test_salesforce_api_error(self):
        datastore = FakeDatastore()
        with patch(
            "salesforce.client.get_salesforce_access_token",
            return_value=("secret-access-token", INSTANCE),
        ), patch(
            "salesforce.bulk_results.requests.get",
            return_value=csv_response(
                [{"message": "Invalid job", "errorCode": "INVALID_JOB"}],
                status=404,
                content_type="application/json",
            ),
        ):
            with self.assertRaises(SalesforceBulkError) as raised:
                download_salesforce_query_results(
                    datastore,
                    CONNECTION,
                    SCAN,
                    dict(BULK_ROW),
                    user_id="user-1",
                    folder=FakeFolder(),
                )
        self.assertEqual(raised.exception.code, "PROVIDER_JOB_NOT_FOUND")
        self.assertNotIn("secret-access-token", str(raised.exception))
        self.assertEqual(
            datastore.tables["bulk_read_jobs"].updates[-1]["status"],
            "DOWNLOAD_RETRYABLE",
        )

    def test_token_refresh_path(self):
        _, _, _, token_fn, get_fn = self._download(
            [csv_response(PAGE_ONE, locator="null")]
        )
        token_fn.assert_called_once_with(ANY, CONNECTION)
        headers = get_fn.call_args.kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Bearer rotated-access-token")
        self.assertEqual(headers["Accept"], "text/csv")
        self.assertNotIn("stored-access-token", headers["Authorization"])

    def test_file_store_persistence(self):
        csv_bytes = combine_salesforce_csv_pages([PAGE_ONE])
        datastore = FakeDatastore()
        folder = FakeFolder(file_id="999")
        artifact = persist_salesforce_csv_artifact(
            datastore, BULK_ROW, csv_bytes, folder, "account.csv"
        )
        self.assertEqual(artifact["source_file_id"], "999")
        self.assertEqual(artifact["source_file_name"], "account.csv")
        self.assertEqual(folder.uploads[0][0], "account.csv")
        self.assertEqual(folder.uploads[0][1], csv_bytes)
        self.assertTrue(
            all(file_type is io.BufferedReader for file_type in folder.received_types)
        )

    def test_upload_file_requires_buffered_reader_like_catalyst_sdk(self):
        csv_bytes = combine_salesforce_csv_pages([PAGE_ONE])
        folder = FakeFolder()

        class BytesReader:
            def __init__(self, data):
                self._data = data

            def read(self, size=-1):
                return self._data

        with self.assertRaises(CatalystFilestoreError) as raised:
            folder.upload_file("account.csv", BytesReader(csv_bytes))
        self.assertEqual(raised.exception.code, "INVALID_FILE_DETAILS")

        artifact = persist_salesforce_csv_artifact(
            FakeDatastore(), BULK_ROW, csv_bytes, folder, "account.csv"
        )
        self.assertEqual(artifact["status"], "DOWNLOADED")
        self.assertEqual(folder.uploads[0][1], csv_bytes)
        self.assertIs(folder.received_types[0], io.BufferedReader)

    def test_file_store_failure(self):
        folder = FakeFolder()
        folder.fail = True
        datastore = FakeDatastore()
        with patch(
            "salesforce.client.get_salesforce_access_token",
            return_value=("stored-access-token", INSTANCE),
        ), patch(
            "salesforce.bulk_results.requests.get",
            return_value=csv_response(PAGE_ONE, locator="null"),
        ):
            with self.assertRaises(SalesforceBulkError) as raised:
                download_salesforce_query_results(
                    datastore,
                    CONNECTION,
                    SCAN,
                    dict(BULK_ROW),
                    user_id="user-1",
                    folder=folder,
                )
        self.assertEqual(raised.exception.code, "FILESTORE_UPLOAD_FAILED")
        self.assertEqual(
            datastore.tables["bulk_read_jobs"].updates[-1]["status"],
            "DOWNLOAD_UNKNOWN",
        )

    def test_no_token_secret_leakage(self):
        records = []

        class Handler(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        logger = logging.getLogger("salesforce.bulk_results")
        handler = Handler()
        logger.addHandler(handler)
        try:
            with patch(
                "salesforce.client.get_salesforce_access_token",
                return_value=("super-secret-token", INSTANCE),
            ), patch(
                "salesforce.bulk_results.requests.get",
                return_value=csv_response(
                    [{"errorCode": "INVALID_SESSION_ID", "message": "expired"}],
                    status=401,
                    content_type="application/json",
                ),
            ):
                with self.assertRaises(SalesforceBulkError) as raised:
                    download_salesforce_query_results(
                        FakeDatastore(),
                        CONNECTION,
                        SCAN,
                        dict(BULK_ROW),
                        user_id="user-1",
                        folder=FakeFolder(),
                    )
        finally:
            logger.removeHandler(handler)
        self.assertEqual(raised.exception.code, "TOKEN_REFRESH_FAILED")
        blob = " ".join(records) + str(raised.exception)
        self.assertNotIn("super-secret-token", blob)
        self.assertNotIn("stored-refresh-token", blob)

    def test_results_url_uses_provider_job_id(self):
        url = salesforce_query_results_url(INSTANCE, JOB_ID, locator="abc")
        self.assertIn(f"/jobs/query/{JOB_ID}/results", url)
        self.assertIn("locator=abc", url)
        self.assertNotIn("zoho", url)

    def test_already_downloaded_is_idempotent(self):
        bulk = {
            **BULK_ROW,
            "status": "DOWNLOADED",
            "source_file_id": "888",
            "source_file_name": "done.csv",
            "downloaded_record_count": 5,
        }
        result, datastore, folder, _, get_fn = self._download(
            [csv_response(PAGE_ONE, locator="null")],
            bulk_row=bulk,
        )
        self.assertTrue(result["alreadyDownloaded"])
        self.assertEqual(result["downloadedRecordCount"], 5)
        get_fn.assert_not_called()
        self.assertEqual(folder.uploads, [])
        self.assertNotIn("bulk_read_jobs", datastore.tables)

    def test_downloading_status_blocks_retry(self):
        with self.assertRaises(SalesforceBulkError) as raised:
            validate_salesforce_result_download(
                SCAN,
                {**BULK_ROW, "status": "DOWNLOADING"},
                CONNECTION,
                user_id="user-1",
            )
        self.assertEqual(raised.exception.code, "BULK_DOWNLOAD_RETRY_BLOCKED")

    def test_download_unknown_without_source_file_can_retry(self):
        provider_job_id = validate_salesforce_result_download(
            SCAN,
            {**BULK_ROW, "status": "DOWNLOAD_UNKNOWN"},
            CONNECTION,
            user_id="user-1",
        )
        self.assertEqual(provider_job_id, JOB_ID)
        result, datastore, folder, _, get_fn = self._download(
            [csv_response(PAGE_ONE, locator="null")],
            bulk_row={**BULK_ROW, "status": "DOWNLOAD_UNKNOWN"},
        )
        self.assertFalse(result["alreadyDownloaded"])
        self.assertEqual(result["status"], "DOWNLOADED")
        get_fn.assert_called_once()
        self.assertEqual(folder.uploads[0][1], PAGE_ONE)
        self.assertTrue(
            any(
                row.get("status") == "DOWNLOADED"
                for row in datastore.tables["bulk_read_jobs"].updates
            )
        )

    def test_download_unknown_with_source_file_is_blocked(self):
        with self.assertRaises(SalesforceBulkError) as raised:
            validate_salesforce_result_download(
                SCAN,
                {
                    **BULK_ROW,
                    "status": "DOWNLOAD_UNKNOWN",
                    "source_file_id": "888",
                },
                CONNECTION,
                user_id="user-1",
            )
        self.assertEqual(raised.exception.code, "BULK_DOWNLOAD_RETRY_BLOCKED")


if __name__ == "__main__":
    unittest.main()
