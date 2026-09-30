import json
import os
import re
import sys
import types
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS_ROOT = ROOT / "functions"
HTTP_FUNCTION = FUNCTIONS_ROOT / "ai_data_analytics_function"
ZOHO_WORKER = FUNCTIONS_ROOT / "ai_data_analytics_worker"
SF_WORKER = FUNCTIONS_ROOT / "ai_data_analytics_salesforce_worker"
SHARED_WORKER = FUNCTIONS_ROOT / "_shared" / "worker"

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
            if isinstance(self.payload, str):
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

sys.path.insert(0, str(ZOHO_WORKER))
sys.path.insert(0, str(HTTP_FUNCTION))

from analytics.fix_export import download_fix_export, get_fix_export
from pipeline.fix_export_enqueue import (
    EXPORT_TASK_TYPE,
    enqueue_fix_export,
    fix_export_task_key,
    normalize_fix_export_request,
)
from pipeline import fix_export_enqueue as enqueue_mod
from analytics import fix_export as download_mod
from shared.fix_export import (
    FINDING_PAGE_SIZE,
    XLSX_WORKBOOK_OPTIONS,
    export_fix_xlsx,
)
from storage.extract_store import build_fix_export_object_key, build_fix_object_key


SCAN_ID = "scan_fix_export_1"
TASK_ID = "task_fix_export_1"
SCAN_ROW = {
    "ROWID": "1001",
    "scan_id": SCAN_ID,
    "crm_provider": "zoho",
    "connection_row_id": "5550000000001",
}
SF_SCAN_ROW = {
    **SCAN_ROW,
    "crm_provider": "salesforce",
    "connection_row_id": "7770000000001",
}
MODULE_ROW = {
    "ROWID": "2001",
    "module_api_name": "Leads",
    "field_allowlist_json": json.dumps(["Email", "Company"]),
    "field_metadata_json": json.dumps(
        [
            {"apiName": "Email", "label": "Email"},
            {"apiName": "Company", "label": "Company"},
        ]
    ),
}
BATCH_ROW = {"ROWID": "3001", "batch_number": 1}
ANALYTICS_ROW = {
    "status": "COMPUTED",
    "metric_group": "record_findings",
    "schema_version": "record-findings-v5",
    "module_api_name": "Leads",
    "aggregate_json": json.dumps({"measured": True, "affectedRecordCount": 2, "issueCount": 2}),
}
EXPORT_REQUEST = {
    "module": "Leads",
    "q": "",
    "owners": [],
    "severity": "",
    "issueType": "",
    "schemaVersion": "record-findings-v5",
    "version": "fix-export-v1",
}


def _jsonl(lines):
    return "".join(json.dumps(line, separators=(",", ":")) + "\n" for line in lines).encode("utf-8")


def _payload(response):
    if hasattr(response, "get_json"):
        try:
            return response.get_json()
        except Exception:
            pass
    if isinstance(response.payload, (bytes, bytearray)):
        try:
            return json.loads(response.payload.decode("utf-8"))
        except Exception:
            return response.payload
    if isinstance(response.payload, str):
        return json.loads(response.payload)
    return response.payload


class FakeBucket:
    def __init__(self):
        self.uploads = []
        self.objects = {}
        self.deleted_paths = []

    def put_object(self, key, body, options=None):
        if options and options.get("extract_upload"):
            raise AssertionError("extract_upload must not be used")
        data = body.read() if hasattr(body, "read") else body
        self.uploads.append((key, data))
        self.objects[key] = data
        return True

    def get_object(self, key):
        if key not in self.objects:
            error = RuntimeError("not found")
            error.status_code = 404
            raise error
        return self.objects[key]

    def delete_path(self, path):
        self.deleted_paths.append(path)
        prefix = str(path)
        for key in list(self.objects):
            if key.startswith(prefix):
                del self.objects[key]


class FakeTable:
    def __init__(self):
        self.rows = []
        self.updated = []

    def insert_row(self, row):
        stored = {"ROWID": str(len(self.rows) + 9001), **row}
        self.rows.append(stored)
        return stored

    def update_row(self, row):
        self.updated.append(dict(row))
        row_id = str(row.get("ROWID") or "")
        for existing in self.rows:
            if str(existing.get("ROWID") or "") == row_id:
                existing.update(row)
                return existing
        return row


class FakeDatastore:
    def __init__(self, table=None):
        self.table_obj = table or FakeTable()

    def table(self, name):
        del name
        return self.table_obj


class FakeJob:
    def __init__(self):
        self.submitted = []

    def submit_job(self, payload):
        self.submitted.append(payload)
        return {"id": "job_fix_1"}


class FakeApp:
    def __init__(self, zcql, bucket=None, table=None):
        self._zcql = zcql
        self.bucket = bucket or FakeBucket()
        self.datastore_obj = FakeDatastore(table)
        self.job = FakeJob()

    def zcql(self):
        return self._zcql

    def datastore(self):
        return self.datastore_obj

    def job_scheduling(self):
        return types.SimpleNamespace(job=self.job)

    def stratus(self):
        bucket = self.bucket

        class Stratus:
            def bucket(self, name):
                del name
                return bucket

        return Stratus()

    def authentication(self):
        return types.SimpleNamespace(
            get_current_user=lambda: {"user_id": "user-1"}
        )


class FakeFindingsZcql:
    def __init__(self, findings):
        self.findings = list(findings)
        self.queries = []

    def execute_query(self, query):
        self.queries.append(query)
        if "from scan_jobs" in query:
            return [{"scan_jobs": SCAN_ROW}]
        if "from scan_module_runs" in query:
            return [{"scan_module_runs": MODULE_ROW}]
        if "from processing_batches" in query:
            return [{"processing_batches": BATCH_ROW}]
        if "from record_quality_findings" in query:
            cursor = 0
            match = re.search(r"ROWID > (\d+)", query)
            if match:
                cursor = int(match.group(1))
            limit = FINDING_PAGE_SIZE
            limit_match = re.search(r"limit 0,(\d+)", query)
            if limit_match:
                limit = int(limit_match.group(1))
            page = [
                row
                for row in self.findings
                if int(row["ROWID"]) > cursor
            ][:limit]
            return [{"record_quality_findings": row} for row in page]
        return []


def _finding(row_id, crm_record_id, display_name, jsonl_line, issue_type_keys="INVALID_EMAIL"):
    return {
        "ROWID": str(row_id),
        "crm_record_id": crm_record_id,
        "display_name": display_name,
        "owner_key": "owner_a",
        "highest_severity": "HIGH",
        "processing_batch_row_id": "3001",
        "jsonl_line": jsonl_line,
        "issue_type_keys": issue_type_keys,
        "module_api_name": "Leads",
        "schema_version": "record-findings-v5",
        "issue_count": 1,
        "status": "DETECTED",
        "scan_row_id": "1001",
    }


def _sidecar_lines():
    return [
        {
            "crmRecordId": "crm_001",
            "cells": {"Email": "john.smith@", "Company": "Acme"},
            "issues": [
                {
                    "fieldApiName": "Email",
                    "issueType": "INVALID_EMAIL",
                    "severity": "HIGH",
                    "messageCode": "INVALID_EMAIL_FORMAT",
                    "fieldLabel": "Email",
                }
            ],
        },
        {
            "crmRecordId": "crm_002",
            "cells": {"Email": "", "Company": "Northwind"},
            "issues": [
                {
                    "fieldApiName": "Email",
                    "issueType": "MISSING_VALUE",
                    "severity": "MEDIUM",
                    "messageCode": "BUSINESS_CRITICAL_VALUE_MISSING",
                    "fieldLabel": "Email",
                }
            ],
        },
    ]


def _json_request(payload):
    return types.SimpleNamespace(get_json=lambda silent=True: payload)


class FixExportWorkerTests(unittest.TestCase):
    def test_constant_memory_workbook_options(self):
        self.assertTrue(XLSX_WORKBOOK_OPTIONS.get("constant_memory"))

    def test_worker_cursors_findings_and_writes_highlighted_xlsx(self):
        zcql = FakeFindingsZcql(
            [
                _finding(11, "crm_001", "Acme Lead", 0),
                _finding(12, "crm_002", "Northwind", 1, "MISSING_VALUE"),
            ]
        )
        bucket = FakeBucket()
        sidecar_key = build_fix_object_key(SCAN_ID, "Leads", 1)
        bucket.objects[sidecar_key] = _jsonl(_sidecar_lines())
        table = FakeTable()
        table.rows.append({"ROWID": "44", "task_id": TASK_ID})
        app = FakeApp(zcql, bucket=bucket, table=table)
        task_row = {
            "ROWID": "44",
            "task_id": TASK_ID,
            "scan_row_id": "1001",
            "task_type": EXPORT_TASK_TYPE,
            "request_json": json.dumps(EXPORT_REQUEST),
        }
        with patch.dict(os.environ, {"STRATUS_BUCKET_NAME": "crm-extracts"}), patch(
            "shared.fix_export.FINDING_PAGE_SIZE", 1
        ):
            result = export_fix_xlsx(app, task_row)

        expected_key = f"exports/{SCAN_ID}/fix/exports/{TASK_ID}.xlsx"
        self.assertEqual(result["objectKey"], expected_key)
        self.assertEqual(result["recordCount"], 2)
        self.assertEqual(result["issueCount"], 2)
        self.assertEqual(build_fix_export_object_key(SCAN_ID, TASK_ID), expected_key)
        self.assertEqual(bucket.uploads[0][0], expected_key)
        finding_queries = [query for query in zcql.queries if "record_quality_findings" in query]
        self.assertGreaterEqual(len(finding_queries), 2)
        self.assertIn("ROWID > 11", finding_queries[1])
        self.assertIn("limit 0,1", finding_queries[0])
        self.assertNotIn("get_extract", "".join(zcql.queries))

        workbook = bucket.objects[expected_key]
        self.assertTrue(workbook.startswith(b"PK"))
        with zipfile.ZipFile(BytesIO(workbook)) as archive:
            names = set(archive.namelist())
            self.assertIn("xl/worksheets/sheet1.xml", names)
            self.assertIn("xl/worksheets/sheet2.xml", names)
            workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
            self.assertIn("Records", workbook_xml)
            self.assertIn("Defects", workbook_xml)
            combined = b"".join(archive.read(name) for name in names)
        self.assertIn(b"john.smith@", combined)
        self.assertIn(b"INVALID_EMAIL", combined)
        self.assertIn(b"FBEAE8", combined)
        self.assertNotIn(b"Invalid email replaces", combined)
        updates = [row for row in table.updated if row.get("result_file_key")]
        self.assertEqual(updates[-1]["result_file_key"], expected_key)

    def test_zoho_dispatcher_routes_export_task(self):
        dispatcher = (ZOHO_WORKER / "worker" / "dispatcher.py").read_text(encoding="utf-8")
        self.assertIn('task_type == "EXPORT_FIX_XLSX"', dispatcher)
        self.assertIn("from shared.fix_export import export_fix_xlsx", dispatcher)
        self.assertIn("return export_fix_xlsx(app, task_row)", dispatcher)


class FixExportEnqueueTests(unittest.TestCase):
    def test_normalize_filters_and_task_key_are_stable(self):
        left = normalize_fix_export_request(
            {"module": "Leads", "owners": ["b", "a"], "severity": "high", "issueType": "INVALID_EMAIL"}
        )
        right = normalize_fix_export_request(
            {"module": "Leads", "owners": ["a", "b"], "severity": "HIGH", "issueType": "INVALID_EMAIL"}
        )
        self.assertEqual(left["owners"], ["a", "b"])
        self.assertEqual(fix_export_task_key(SCAN_ID, left), fix_export_task_key(SCAN_ID, right))

    def test_enqueue_does_not_hydrate_findings_and_submits_zoho_worker(self):
        table = FakeTable()
        datastore = FakeDatastore(table)
        zcql = MagicMock()
        zcql.execute_query.return_value = []
        app = FakeApp(zcql, table=table)
        env = {
            "ANALYTICS_WORKER_JOB_POOL_NAME": "zoho-pool",
            "ANALYTICS_WORKER_FUNCTION_NAME": "ai_data_analytics_worker",
            "SALESFORCE_WORKER_JOB_POOL_NAME": "sf-pool",
            "SALESFORCE_WORKER_FUNCTION_NAME": "ai_data_analytics_salesforce_worker",
        }
        with patch.object(enqueue_mod, "find_owned_scan", return_value=SCAN_ROW), patch.object(
            enqueue_mod, "get_current_user_id", return_value="user-1"
        ), patch.object(
            enqueue_mod,
            "find_analytics_results",
            return_value=[ANALYTICS_ROW],
        ), patch(
            "zcatalyst_sdk.initialize", return_value=app
        ), patch.dict(os.environ, env, clear=False):
            response = enqueue_fix_export(
                _json_request({"module": "Leads", "q": "Acme", "owners": ["owner_a"]}),
                datastore,
                SCAN_ID,
            )
        payload = _payload(response)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(payload["taskType"], EXPORT_TASK_TYPE)
        self.assertEqual(payload["taskStatus"], "QUEUED")
        self.assertFalse(payload["alreadyQueued"])
        self.assertEqual(app.job.submitted[0]["jobpool_name"], "zoho-pool")
        self.assertEqual(
            app.job.submitted[0]["params"],
            {"taskId": table.rows[0]["task_id"]},
        )
        self.assertIn("request_json", table.rows[0])
        zcql.execute_query.assert_called()
        for query, *_ in [call.args for call in zcql.execute_query.call_args_list]:
            self.assertNotIn("record_quality_findings", query)

    def test_enqueue_reuses_in_flight_and_succeeded_export(self):
        task_key = fix_export_task_key(SCAN_ID, normalize_fix_export_request({"module": "Leads"}))
        queued = {
            "ROWID": "8",
            "task_id": "task_queued",
            "task_key": task_key,
            "status": "QUEUED",
            "enqueued_at": "2099-01-01 00:00:00",
        }
        succeeded = {
            "ROWID": "9",
            "task_id": "task_done",
            "task_key": task_key,
            "status": "SUCCEEDED",
            "result_file_key": f"exports/{SCAN_ID}/fix/exports/task_done.xlsx",
        }
        zcql = MagicMock()
        zcql.execute_query.side_effect = [
            [{"pipeline_tasks": queued}],
            [{"pipeline_tasks": succeeded}],
        ]
        app = FakeApp(zcql)
        env = {
            "ANALYTICS_WORKER_JOB_POOL_NAME": "zoho-pool",
            "ANALYTICS_WORKER_FUNCTION_NAME": "ai_data_analytics_worker",
        }
        with patch.object(enqueue_mod, "find_owned_scan", return_value=SCAN_ROW), patch.object(
            enqueue_mod, "get_current_user_id", return_value="user-1"
        ), patch.object(
            enqueue_mod,
            "find_analytics_results",
            return_value=[ANALYTICS_ROW],
        ), patch(
            "zcatalyst_sdk.initialize", return_value=app
        ), patch.dict(os.environ, env, clear=False):
            in_flight = enqueue_fix_export(_json_request({"module": "Leads"}), FakeDatastore(), SCAN_ID)
            done = enqueue_fix_export(_json_request({"module": "Leads"}), FakeDatastore(), SCAN_ID)
        self.assertEqual(in_flight.status_code, 202)
        self.assertTrue(_payload(in_flight)["alreadyQueued"])
        self.assertEqual(done.status_code, 200)
        self.assertTrue(_payload(done)["alreadyExported"])
        self.assertEqual(app.job.submitted, [])

    def test_enqueue_salesforce_scan_uses_salesforce_pool(self):
        table = FakeTable()
        zcql = MagicMock()
        zcql.execute_query.return_value = []
        app = FakeApp(zcql, table=table)
        env = {
            "ANALYTICS_WORKER_JOB_POOL_NAME": "zoho-pool",
            "ANALYTICS_WORKER_FUNCTION_NAME": "ai_data_analytics_worker",
            "SALESFORCE_WORKER_JOB_POOL_NAME": "sf-pool",
            "SALESFORCE_WORKER_FUNCTION_NAME": "ai_data_analytics_salesforce_worker",
        }
        with patch.object(enqueue_mod, "find_owned_scan", return_value=SF_SCAN_ROW), patch.object(
            enqueue_mod, "get_current_user_id", return_value="user-1"
        ), patch.object(
            enqueue_mod,
            "find_analytics_results",
            return_value=[ANALYTICS_ROW],
        ), patch(
            "zcatalyst_sdk.initialize", return_value=app
        ), patch.dict(os.environ, env, clear=False):
            response = enqueue_fix_export(_json_request({"module": "Leads"}), FakeDatastore(table), SCAN_ID)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(app.job.submitted[0]["jobpool_name"], "sf-pool")
        self.assertEqual(app.job.submitted[0]["target_name"], "ai_data_analytics_salesforce_worker")

    def test_cross_tenant_enqueue_is_404(self):
        with patch.object(enqueue_mod, "find_owned_scan", return_value=None), patch.object(
            enqueue_mod, "get_current_user_id", return_value="other-user"
        ), patch(
            "zcatalyst_sdk.initialize",
            return_value=FakeApp(MagicMock()),
        ):
            response = enqueue_fix_export(_json_request({"module": "Leads"}), FakeDatastore(), SCAN_ID)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(_payload(response)["error"]["code"], "SCAN_NOT_FOUND")


class FixExportDownloadTests(unittest.TestCase):
    def test_download_requires_succeeded_and_owned_scan(self):
        object_key = f"exports/{SCAN_ID}/fix/exports/{TASK_ID}.xlsx"
        bucket = FakeBucket()
        bucket.objects[object_key] = b"PK-xlsx"
        task_row = {
            "ROWID": "44",
            "task_id": TASK_ID,
            "status": "QUEUED",
            "result_file_key": object_key,
            "request_json": json.dumps(EXPORT_REQUEST),
        }
        zcql = MagicMock()
        zcql.execute_query.return_value = [{"pipeline_tasks": task_row}]
        app = FakeApp(zcql, bucket=bucket)
        with patch.object(download_mod, "find_owned_scan", return_value=SCAN_ROW), patch.object(
            download_mod, "get_current_user_id", return_value="user-1"
        ), patch("zcatalyst_sdk.initialize", return_value=app), patch.dict(
            os.environ, {"STRATUS_BUCKET_NAME": "crm-extracts"}
        ):
            not_ready = download_fix_export(object(), FakeDatastore(), SCAN_ID, TASK_ID)
        self.assertEqual(not_ready.status_code, 409)
        self.assertEqual(_payload(not_ready)["error"]["code"], "EXPORT_NOT_READY")

        task_row["status"] = "SUCCEEDED"
        with patch.object(download_mod, "find_owned_scan", return_value=SCAN_ROW), patch.object(
            download_mod, "get_current_user_id", return_value="user-1"
        ), patch("zcatalyst_sdk.initialize", return_value=app), patch.dict(
            os.environ, {"STRATUS_BUCKET_NAME": "crm-extracts"}
        ):
            ready = download_fix_export(object(), FakeDatastore(), SCAN_ID, TASK_ID)
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.payload, b"PK-xlsx")
        self.assertEqual(
            ready.headers["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn("attachment;", ready.headers["Content-Disposition"])
        self.assertIn(f"{TASK_ID}.xlsx", ready.headers["Content-Disposition"])
        self.assertNotIn("http", ready.headers.get("Content-Disposition", "").lower())

    def test_status_and_download_are_404_for_other_tenant(self):
        with patch.object(download_mod, "find_owned_scan", return_value=None), patch.object(
            download_mod, "get_current_user_id", return_value="other-user"
        ), patch(
            "zcatalyst_sdk.initialize",
            return_value=FakeApp(MagicMock()),
        ):
            status = get_fix_export(object(), FakeDatastore(), SCAN_ID, TASK_ID)
            download = download_fix_export(object(), FakeDatastore(), SCAN_ID, TASK_ID)
        self.assertEqual(status.status_code, 404)
        self.assertEqual(download.status_code, 404)
        self.assertEqual(_payload(status)["error"]["code"], "SCAN_NOT_FOUND")


class FixExportPackagingTests(unittest.TestCase):
    def test_xlsxwriter_is_worker_only(self):
        http_requirements = (HTTP_FUNCTION / "requirements.txt").read_text(encoding="utf-8")
        zoho_requirements = (ZOHO_WORKER / "requirements.txt").read_text(encoding="utf-8")
        sf_requirements = (SF_WORKER / "requirements.txt").read_text(encoding="utf-8")
        self.assertNotIn("xlsxwriter", http_requirements.lower())
        self.assertIn("xlsxwriter", zoho_requirements.lower())
        self.assertIn("xlsxwriter", sf_requirements.lower())

    def test_shared_worker_module_is_packaged(self):
        source = (SHARED_WORKER / "fix_export.py").read_bytes()
        self.assertEqual(source, (ZOHO_WORKER / "shared" / "fix_export.py").read_bytes())
        self.assertEqual(source, (SF_WORKER / "shared" / "fix_export.py").read_bytes())

    def test_salesforce_worker_allows_export_task_type(self):
        main_text = (SF_WORKER / "main.py").read_text(encoding="utf-8")
        resolve_text = (SF_WORKER / "task_resolve.py").read_text(encoding="utf-8")
        self.assertIn("EXPORT_FIX_XLSX", main_text)
        self.assertIn("export_fix_xlsx", main_text)
        self.assertIn("EXPORT_FIX_XLSX", resolve_text)


if __name__ == "__main__":
    unittest.main()
