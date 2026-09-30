import hashlib
import io
import json
import os
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS_ROOT = ROOT / "functions"
SHARED_ROOT = FUNCTIONS_ROOT / "_shared"
HTTP_FUNCTION = FUNCTIONS_ROOT / "ai_data_analytics_function"
ZOHO_WORKER = FUNCTIONS_ROOT / "ai_data_analytics_worker"
SF_WORKER = FUNCTIONS_ROOT / "ai_data_analytics_salesforce_worker"

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
    stub = types.ModuleType("zcatalyst_sdk")
    stub.initialize = lambda: None
    sys.modules["zcatalyst_sdk"] = stub

sys.path.insert(0, str(SHARED_ROOT))
sys.path.insert(0, str(HTTP_FUNCTION))

from storage.extract_store import (
    ExtractStorageError,
    build_fix_export_object_key,
    build_fix_object_key,
    build_object_key,
    delete_scan_extracts,
    download_extract_to_tempfile,
    put_extract,
)
from storage.locator import (
    BACKEND_FILESTORE,
    BACKEND_STRATUS,
    has_extract_locator,
    resolve_extract_locator,
)
from common.core import MAX_FILESTORE_UPLOAD_BYTES
from orchestration.choose import choose_action


class FakeStream:
    def __init__(self, data):
        self._data = data

    def iter_content(self, chunk_size=1024):
        yield self._data


class FakeFolder:
    def __init__(self):
        self.uploads = []
        self.files = {}

    def upload_file(self, name, file_obj):
        raise AssertionError("File Store upload must not be called")

    def get_file_stream(self, file_id):
        return FakeStream(self.files[str(file_id)])


class FakeBucket:
    def __init__(self):
        self.uploads = []
        self.objects = {}
        self.deleted_paths = []
        self.fail = False
        self.missing = False

    def put_object(self, key, body, options=None):
        if options and options.get("extract_upload"):
            raise AssertionError("extract_upload must not be used")
        if self.fail:
            raise RuntimeError("stratus unavailable")
        data = body.read() if hasattr(body, "read") else body
        self.uploads.append((key, data, options, type(body)))
        self.objects[key] = data
        return True

    def get_object(self, key):
        if self.missing or key not in self.objects:
            error = RuntimeError("not found")
            error.status_code = 404
            raise error
        return self.objects[key]

    def delete_path(self, path):
        if self.missing:
            error = RuntimeError("not found")
            error.status_code = 404
            raise error
        self.deleted_paths.append(path)
        prefix = str(path)
        for key in list(self.objects):
            if key.startswith(prefix):
                del self.objects[key]
        return {"deleted": True}


class FakeApp:
    def __init__(self, bucket=None, folder=None):
        self._bucket = bucket or FakeBucket()
        self._folder = folder or FakeFolder()

    def stratus(self):
        return types.SimpleNamespace(bucket=lambda _name: self._bucket)

    def filestore(self):
        return types.SimpleNamespace(folder=lambda _id: self._folder)


class LocatorTests(unittest.TestCase):
    def test_stratus_key_preferred_over_legacy_id(self):
        locator = resolve_extract_locator(
            {
                "source_file_key": "exports/scan/job_provider.zip",
                "source_file_id": "48465000000012345",
            }
        )
        self.assertEqual(locator.backend, BACKEND_STRATUS)
        self.assertEqual(locator.locator, "exports/scan/job_provider.zip")
        self.assertTrue(
            has_extract_locator(
                {
                    "source_file_key": "exports/scan/job_provider.zip",
                    "source_file_id": "48465000000012345",
                }
            )
        )

    def test_legacy_file_store_fallback(self):
        locator = resolve_extract_locator({"source_file_id": "888"})
        self.assertEqual(locator.backend, BACKEND_FILESTORE)
        self.assertEqual(locator.locator, "888")

    def test_missing_locator(self):
        self.assertIsNone(resolve_extract_locator({}))
        self.assertIsNone(resolve_extract_locator({"source_file_id": "exports/scan/x.zip"}))
        self.assertIsNone(resolve_extract_locator({"source_file_key": "  "}))
        self.assertFalse(has_extract_locator({"source_file_id": "abc"}))

    def test_does_not_use_isdigit_on_source_file_key(self):
        locator = resolve_extract_locator(
            {"source_file_key": "exports/scan/bulk_zoho.zip"}
        )
        self.assertEqual(locator.backend, BACKEND_STRATUS)
        self.assertFalse(locator.locator.isdigit())

    def test_object_key_shape(self):
        self.assertEqual(
            build_object_key("scan_1", "bulk_2", "job_3", "zip"),
            "exports/scan_1/bulk_2_job_3.zip",
        )
        self.assertEqual(
            build_object_key("scan_1", "bulk_2", "job_3", "csv"),
            "exports/scan_1/bulk_2_job_3.csv",
        )

    def test_fix_sidecar_object_key_shape(self):
        self.assertEqual(
            build_fix_object_key("scan_1", "Leads", 1),
            "exports/scan_1/fix/Leads/batch-1.jsonl",
        )
        self.assertEqual(
            build_fix_object_key("scan_1", "Account", "12"),
            "exports/scan_1/fix/Account/batch-12.jsonl",
        )
        with self.assertRaises(ExtractStorageError):
            build_fix_object_key("scan_1", "Leads/../x", 1)
        with self.assertRaises(ExtractStorageError):
            build_fix_object_key("scan_1", "Leads", 0)
        with self.assertRaises(ExtractStorageError):
            build_object_key("scan_1", "bulk_2", "job_3", "jsonl")

    def test_fix_export_object_key_shape(self):
        self.assertEqual(
            build_fix_export_object_key("scan_1", "task_abc"),
            "exports/scan_1/fix/exports/task_abc.xlsx",
        )
        with self.assertRaises(ExtractStorageError):
            build_fix_export_object_key("scan_1", "task/../x")
        with self.assertRaises(ExtractStorageError):
            build_fix_export_object_key("scan_1/x", "task_abc")


class ExtractStoreTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ,
            {
                "STRATUS_BUCKET_NAME": "crm-extracts",
                "BULK_EXPORT_FOLDER_ID": "12345",
            },
        )
        self.env.start()
        self.app = FakeApp()

    def tearDown(self):
        self.env.stop()

    def test_put_extract_does_not_call_file_store(self):
        payload = b"zip-bytes"
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "export.zip")
            with open(path, "wb") as handle:
                handle.write(payload)
            with open(path, "rb") as handle:
                key = put_extract("exports/scan/bulk_job.zip", handle, app=self.app)
        self.assertEqual(key, "exports/scan/bulk_job.zip")
        self.assertEqual(self.app._bucket.uploads[0][0], key)
        self.assertEqual(self.app._bucket.uploads[0][1], payload)
        self.assertIsNone(self.app._bucket.uploads[0][2])
        self.assertIs(self.app._bucket.uploads[0][3], io.BufferedReader)
        self.assertEqual(self.app._folder.uploads, [])

    def test_stratus_download_and_legacy_file_store_download(self):
        checksum = hashlib.sha256(b"stratus").hexdigest()
        self.app._bucket.objects["exports/scan/a_b.zip"] = b"stratus"
        path = download_extract_to_tempfile(
            {
                "source_file_key": "exports/scan/a_b.zip",
                "source_file_id": "9",
                "source_file_checksum": checksum,
            },
            app=self.app,
        )
        try:
            with open(path, "rb") as handle:
                self.assertEqual(handle.read(), b"stratus")
        finally:
            os.remove(path)

        legacy_checksum = hashlib.sha256(b"filestore").hexdigest()
        self.app._folder.files["9"] = b"filestore"
        path = download_extract_to_tempfile(
            {"source_file_id": "9", "source_file_checksum": legacy_checksum},
            app=self.app,
        )
        try:
            with open(path, "rb") as handle:
                self.assertEqual(handle.read(), b"filestore")
        finally:
            os.remove(path)

    def test_checksum_mismatch(self):
        self.app._bucket.objects["exports/scan/a_b.zip"] = b"stratus"
        with self.assertRaises(ValueError) as raised:
            download_extract_to_tempfile(
                {
                    "source_file_key": "exports/scan/a_b.zip",
                    "source_file_checksum": "deadbeef",
                },
                app=self.app,
            )
        self.assertIn("checksum", str(raised.exception).lower())

    def test_scan_prefix_deletion_is_idempotent_and_skips_file_store(self):
        self.app._bucket.objects["exports/scan_abc/one.zip"] = b"one"
        self.app._folder.files["888"] = b"legacy"
        prefix = delete_scan_extracts("scan_abc", app=self.app)
        self.assertEqual(prefix, "exports/scan_abc/")
        self.assertEqual(self.app._bucket.deleted_paths, ["exports/scan_abc/"])
        self.assertNotIn("exports/scan_abc/one.zip", self.app._bucket.objects)
        self.assertEqual(self.app._folder.files["888"], b"legacy")

        self.app._bucket.missing = True
        again = delete_scan_extracts("scan_abc", app=self.app)
        self.assertEqual(again, "exports/scan_abc/")
        self.assertEqual(self.app._folder.files["888"], b"legacy")

    def test_hundred_mb_limit_constant_unchanged(self):
        self.assertEqual(MAX_FILESTORE_UPLOAD_BYTES, 100 * 1024 * 1024)
        source = (SHARED_ROOT / "salesforce" / "bulk_results.py").read_text(encoding="utf-8")
        self.assertIn("MAX_FILESTORE_UPLOAD_BYTES = 100 * 1024 * 1024", source)
        self.assertIn("BULK_EXPORT_TOO_LARGE", source)
        download_source = (SHARED_ROOT / "bulk_read" / "download.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("BULK_EXPORT_TOO_LARGE", download_source)
        self.assertNotIn("folder.upload_file", download_source)
        self.assertIn("source_file_key", download_source)


class ChooseAndPrepareTests(unittest.TestCase):
    def _state(self, bulk):
        return {
            "scan": {"status": "EXTRACTING"},
            "modules": [{"ROWID": "1"}],
            "bulk_jobs_by_module": {"1": [bulk]},
            "tasks": [],
        }

    def test_choose_accepts_either_locator(self):
        key_bulk = {
            "ROWID": "2",
            "status": "PROCESSING",
            "source_file_key": "exports/scan/bulk_job.zip",
            "provider_page": 0,
            "bulk_job_id": "bulk_1",
        }
        self.assertEqual(choose_action(self._state(key_bulk))["name"], "PROCESS_BATCHES")
        id_bulk = {
            "ROWID": "2",
            "status": "PROCESSING",
            "source_file_id": "888",
            "provider_page": 0,
            "bulk_job_id": "bulk_1",
        }
        self.assertEqual(choose_action(self._state(id_bulk))["name"], "PROCESS_BATCHES")

    def test_choose_without_locator_polls_provider_processing(self):
        bulk = {
            "ROWID": "2",
            "status": "PROCESSING",
            "provider_page": 0,
            "bulk_job_id": "bulk_1",
        }
        self.assertEqual(choose_action(self._state(bulk))["name"], "CHECK_BULK_STATUS")

    def test_prepare_batches_accepts_either_locator(self):
        source = (SHARED_ROOT / "worker" / "prepare_batches.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("has_extract_locator(bulk_row)", source)
        self.assertIn("source_file_checksum", source)


class SalesforceCsvWrapTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ,
            {
                "STRATUS_BUCKET_NAME": "crm-extracts",
                "BULK_EXPORT_FOLDER_ID": "12345",
            },
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_salesforce_csv_is_wrapped_as_zip(self):
        import importlib.util

        if str(SF_WORKER) not in sys.path:
            sys.path.insert(0, str(SF_WORKER))
        module_path = SF_WORKER / "pipeline" / "processing.py"
        spec = importlib.util.spec_from_file_location(
            "sf_worker_processing_extract_tests", module_path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        csv_bytes = b"Id,Name\n1,Acme\n"
        checksum = hashlib.sha256(csv_bytes).hexdigest()
        app = FakeApp()
        app._bucket.objects["exports/scan/bulk_job.csv"] = csv_bytes
        path = module._download_source_zip(
            app,
            {
                "source_file_key": "exports/scan/bulk_job.csv",
                "source_file_checksum": checksum,
            },
        )
        try:
            self.assertTrue(zipfile.is_zipfile(path))
            with zipfile.ZipFile(path, "r") as archive:
                self.assertEqual(archive.namelist(), ["export.csv"])
                self.assertEqual(archive.read("export.csv"), csv_bytes)
        finally:
            os.remove(path)


class RecordsTabLocatorTests(unittest.TestCase):
    def test_proper_and_owner_paths_accept_source_file_key(self):
        from analytics.record_export import list_clean_records, list_owner_analytics

        module_row = {"ROWID": "2001", "module_api_name": "Account"}
        bulk_row = {
            "source_file_key": "exports/scan_1/bulk_job.csv",
            "source_file_checksum": "abc",
        }
        with patch(
            "analytics.record_export.find_module_runs",
            return_value=[module_row],
        ), patch(
            "analytics.record_export.find_bulk_jobs",
            return_value=[bulk_row],
        ), patch(
            "analytics.record_export._clean_records_from_bulk",
            return_value=[{"recordState": "proper"}],
        ) as clean, patch(
            "analytics.record_export._owner_analytics_from_bulk",
            return_value=[{"data": {"ownerName": "Ada"}}],
        ) as owners:
            records = list_clean_records(None, {"ROWID": "1"}, [], {}, {})
            analytics = list_owner_analytics(
                None, {"ROWID": "1"}, "Account", {}
            )
        self.assertEqual(records, [{"recordState": "proper"}])
        self.assertEqual(analytics[0]["data"]["ownerName"], "Ada")
        clean.assert_called_once()
        owners.assert_called_once()

    def test_non_numeric_legacy_id_without_key_is_skipped(self):
        from analytics.record_export import list_clean_records

        with patch(
            "analytics.record_export.find_module_runs",
            return_value=[{"ROWID": "2001", "module_api_name": "Account"}],
        ), patch(
            "analytics.record_export.find_bulk_jobs",
            return_value=[{"source_file_id": "exports/scan/x.csv"}],
        ), patch(
            "analytics.record_export._clean_records_from_bulk",
            return_value=[{"recordState": "proper"}],
        ) as clean:
            records = list_clean_records(None, {"ROWID": "1"}, [], {}, {})
        self.assertEqual(records, [])
        clean.assert_not_called()


class SharedStoragePackagingTests(unittest.TestCase):
    def test_storage_package_exists_in_all_deployable_functions(self):
        names = ("__init__.py", "extract_store.py", "locator.py")
        for dest in (HTTP_FUNCTION, ZOHO_WORKER, SF_WORKER):
            for name in names:
                source = (SHARED_ROOT / "storage" / name).read_bytes()
                copy = (dest / "storage" / name).read_bytes()
                self.assertEqual(source, copy, f"{dest.name}/storage/{name}")


class ScanDeleteTests(unittest.TestCase):
    def _delete_scan(self, bulk_rows, *, bucket=None, folder=None, stratus_env=None):
        from scans import delete as delete_mod

        scan_row = {"ROWID": "11", "scan_id": "scan_abc"}
        folder = folder or FakeFolder()
        bucket = bucket or FakeBucket()
        app = FakeApp(bucket=bucket, folder=folder)

        class FakeRequest:
            def get_json(self, silent=True):
                return {"confirmScanId": "scan_abc"}

        class FakeTable:
            def delete_rows(self, row_ids):
                return row_ids

        class FakeDatastore:
            def table(self, name):
                return FakeTable()

        class FakeZcql:
            def execute_query(self, query):
                if "from pipeline_tasks" in query:
                    return []
                if "from scan_module_runs" in query:
                    return [{"scan_module_runs": {"ROWID": "31"}}]
                if "from bulk_read_jobs" in query:
                    return [{"bulk_read_jobs": row} for row in bulk_rows]
                if "from processing_batches" in query:
                    return []
                if "from record_quality_issues" in query:
                    return []
                if "from record_quality_findings" in query:
                    return []
                if "from owner_batch_aggregates" in query:
                    return []
                if "from analytics_results" in query:
                    return []
                return []

        app.zcql = lambda: FakeZcql()
        env = {} if stratus_env is None else dict(stratus_env)
        with patch.object(delete_mod.zcatalyst_sdk, "initialize", return_value=app), patch(
            "scans.delete.find_owned_scan", return_value=scan_row
        ), patch("scans.delete.get_current_user_id", return_value="user-1"), patch.dict(
            os.environ, env, clear=False
        ):
            response = delete_mod.delete_scan(FakeRequest(), FakeDatastore(), "scan_abc")
        payload = response.get_json() if hasattr(response, "get_json") else None
        if payload is None:
            payload = json.loads(response.payload.decode("utf-8"))
        return response, payload, bucket, folder

    def test_delete_scan_hybrid_stratus_and_file_store_keeps_file_store(self):
        folder = FakeFolder()
        folder.files["888"] = b"legacy"
        bucket = FakeBucket()
        bucket.objects["exports/scan_abc/a_b.zip"] = b"new"
        bucket.objects["exports/scan_abc/fix/exports/task_1.xlsx"] = b"xlsx"
        response, payload, bucket, folder = self._delete_scan(
            [
                {
                    "ROWID": "21",
                    "source_file_key": "exports/scan_abc/a_b.zip",
                    "source_file_id": "888",
                }
            ],
            bucket=bucket,
            folder=folder,
            stratus_env={"STRATUS_BUCKET_NAME": "crm-extracts"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["stratusPrefix"], "exports/scan_abc/")
        self.assertEqual(bucket.deleted_paths, ["exports/scan_abc/"])
        self.assertNotIn("exports/scan_abc/a_b.zip", bucket.objects)
        self.assertNotIn("exports/scan_abc/fix/exports/task_1.xlsx", bucket.objects)
        self.assertEqual(folder.files["888"], b"legacy")
        self.assertIn("888", payload["sourceFileIds"])

    def test_delete_scan_file_store_only_without_stratus_bucket_succeeds(self):
        folder = FakeFolder()
        folder.files["888"] = b"legacy"
        bucket = FakeBucket()
        bucket.fail = True
        response, payload, bucket, folder = self._delete_scan(
            [{"ROWID": "21", "source_file_id": "888"}],
            bucket=bucket,
            folder=folder,
            stratus_env={"STRATUS_BUCKET_NAME": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("error", payload)
        self.assertIsNone(payload.get("stratusPrefix"))
        self.assertEqual(bucket.deleted_paths, [])
        self.assertEqual(folder.files["888"], b"legacy")
        self.assertIn("888", payload["sourceFileIds"])
        self.assertEqual(payload["deleted"]["scan_jobs"], 1)

    def test_delete_scan_stratus_only_removes_prefix_including_fix_exports(self):
        folder = FakeFolder()
        bucket = FakeBucket()
        bucket.objects["exports/scan_abc/a_b.zip"] = b"new"
        bucket.objects["exports/scan_abc/fix/Leads/batch-1.jsonl"] = b"{}\n"
        bucket.objects["exports/scan_abc/fix/exports/task_1.xlsx"] = b"xlsx"
        response, payload, bucket, folder = self._delete_scan(
            [{"ROWID": "21", "source_file_key": "exports/scan_abc/a_b.zip"}],
            bucket=bucket,
            folder=folder,
            stratus_env={"STRATUS_BUCKET_NAME": "crm-extracts"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["stratusPrefix"], "exports/scan_abc/")
        self.assertEqual(bucket.deleted_paths, ["exports/scan_abc/"])
        self.assertEqual(bucket.objects, {})
        self.assertEqual(folder.files, {})
        self.assertEqual(payload["sourceFileIds"], [])


if __name__ == "__main__":
    unittest.main()
