import importlib.util
import io
import json
import hashlib
import logging
import os
import re
import sys
import types
import unittest
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch


WORKER_ROOT = (
    Path(__file__).resolve().parents[1]
    / "functions"
    / "ai_data_analytics_salesforce_worker"
)
FUNCTION_ROOT = (
    Path(__file__).resolve().parents[1]
    / "functions"
    / "ai_data_analytics_function"
)
WORKER_MAIN = WORKER_ROOT / "main.py"

if "zcatalyst_sdk" not in sys.modules:
    zcatalyst_sdk = types.ModuleType("zcatalyst_sdk")
    zcatalyst_sdk.initialize = lambda: None
    sys.modules["zcatalyst_sdk"] = zcatalyst_sdk

for _path in (str(WORKER_ROOT), str(FUNCTION_ROOT)):
    if _path in sys.path:
        sys.path.remove(_path)
sys.path.insert(0, str(FUNCTION_ROOT))
sys.path.insert(0, str(WORKER_ROOT))

from salesforce.bulk_query import SalesforceBulkError


def load_worker():
    spec = importlib.util.spec_from_file_location(
        "ai_data_analytics_salesforce_worker_main",
        WORKER_MAIN,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


worker = load_worker()

# The worker has its own pipeline/ package. Drop it from sys.modules so other
# Salesforce tests can import the HTTP function's pipeline modules.
for _name in list(sys.modules):
    if _name == "pipeline" or _name.startswith("pipeline."):
        del sys.modules[_name]
if str(WORKER_ROOT) in sys.path:
    sys.path.remove(str(WORKER_ROOT))
sys.path.insert(0, str(FUNCTION_ROOT))
sys.path.append(str(WORKER_ROOT))


TASK_ID = "task_sf_123"
SCAN_ID = "scan_sf_abc"
SCAN_ROW_ID = "101"
CONNECTION_ROW_ID = "555"
LIVE_PROVIDER_JOB_ID = "750dN00000G2iyDQAR"
WORKER_ENV = {
    "ANALYTICS_WORKER_JOB_POOL_NAME": "sfDataAnalyticsWorkerPool",
    "ANALYTICS_WORKER_FUNCTION_NAME": "ai_data_analytics_salesforce_worker",
}


def salesforce_task(**overrides):
    row = {
        "ROWID": "9001",
        "task_id": TASK_ID,
        "task_type": worker.SALESFORCE_TASK_TYPE,
        "scan_row_id": SCAN_ROW_ID,
        "status": "PLANNED",
    }
    row.update(overrides)
    return row


def salesforce_scan(**overrides):
    row = {
        "ROWID": SCAN_ROW_ID,
        "scan_id": SCAN_ID,
        "crm_provider": "salesforce",
        "connection_row_id": CONNECTION_ROW_ID,
        "status": "CREATED",
        "clock_field": "CreatedDate",
        "from_utc": "2026-09-09 12:00:00",
        "to_utc": "2026-09-16 12:00:00",
        "depth_policy": "presales",
    }
    row.update(overrides)
    return row


def salesforce_module(api_name="Account", row_id="201", **overrides):
    fields = ["Id", "Name", "CreatedDate", "LastModifiedDate"]
    if api_name == "Opportunity":
        fields = ["Id", "Name", "StageName", "CreatedDate", "LastModifiedDate"]
    row = {
        "ROWID": row_id,
        "scan_row_id": SCAN_ROW_ID,
        "scan_module_id": f"smod_{api_name.lower()}",
        "module_api_name": api_name,
        "status": "PLANNED",
        "field_allowlist_json": json.dumps(fields),
        "field_plan_hash": f"plan_{api_name}",
        "criteria_hash": f"crit_{api_name}",
    }
    row.update(overrides)
    return row


def salesforce_connection(**overrides):
    row = {
        "ROWID": CONNECTION_ROW_ID,
        "user_id": "owner-1",
        "status": "connected",
        "access_token": "sf_access_token_LIVE_VALUE_do_not_log",
        "refresh_token": "sf_refresh_token_LIVE_VALUE_do_not_log",
    }
    row.update(overrides)
    return row


class FakeTable:
    def __init__(self):
        self.inserts = []
        self.updates = []
        self._next = 1
        self.fail_on = None

    def insert_row(self, row):
        stored = dict(row)
        stored.setdefault("ROWID", str(self._next))
        self._next += 1
        self.inserts.append(stored)
        return stored

    def insert_rows(self, rows):
        return [self.insert_row(row) for row in rows]

    def delete_rows(self, row_ids):
        ids = {str(row_id) for row_id in row_ids}
        self.inserts = [
            row for row in self.inserts if str(row.get("ROWID")) not in ids
        ]
        return list(row_ids)

    def update_row(self, row):
        if self.fail_on and self.fail_on(row):
            raise RuntimeError("persist failed")
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


class FakeJob:
    def __init__(self):
        self.submitted = []

    def submit_job(self, payload):
        self.submitted.append(payload)
        return {"id": "catalyst_sf_job_1"}


class FakeExportStream:
    def __init__(self, data):
        self._data = data

    def iter_content(self, chunk_size=1024):
        yield self._data


class CatalystFilestoreError(Exception):
    """Mirrors zcatalyst_sdk.exceptions.CatalystFilestoreError."""

    def __init__(self, code, message=""):
        self.code = code
        super().__init__(message or code)


class FakeExportFolder:
    def __init__(self):
        self.uploads = []
        self.files = {}

    def upload_file(self, name, file_obj):
        if not isinstance(file_obj, io.BufferedReader):
            raise CatalystFilestoreError(
                "INVALID_FILE_DETAILS",
                "Code must be an instance of BufferReader and cannot be empty",
            )
        data = file_obj.read() if hasattr(file_obj, "read") else file_obj
        file_id = str(8000 + len(self.uploads) + 1)
        self.uploads.append((name, data))
        self.files[file_id] = data
        return {"id": file_id}

    def get_file_stream(self, file_id):
        return FakeExportStream(self.files[str(file_id)])


class FakeStratusBucket:
    def __init__(self):
        self.uploads = []
        self.objects = {}
        self.deleted_paths = []
        self.fail = False

    def put_object(self, key, body, options=None):
        if options and options.get("extract_upload"):
            raise AssertionError("extract_upload must not be used")
        if self.fail:
            raise RuntimeError("stratus unavailable")
        data = body.read() if hasattr(body, "read") else body
        self.uploads.append((key, data, type(body)))
        self.objects[key] = data
        return True

    def get_object(self, key):
        return self.objects[key]

    def delete_path(self, path):
        self.deleted_paths.append(path)
        prefix = str(path)
        for key in list(self.objects):
            if key.startswith(prefix):
                del self.objects[key]
        return {"deleted": True}


class FakeZcql:
    def __init__(
        self,
        tasks=None,
        scans=None,
        salesforce_connections=None,
        zoho_connections=None,
        modules=None,
        bulk_jobs=None,
        datastore=None,
    ):
        self.tasks = {row["task_id"]: row for row in (tasks or [])}
        self.scans = {str(row["ROWID"]): row for row in (scans or [])}
        self.salesforce_connections = {
            str(row["ROWID"]): row for row in (salesforce_connections or [])
        }
        self.zoho_connections = {
            str(row["ROWID"]): row for row in (zoho_connections or [])
        }
        self.modules = list(modules or [])
        self.bulk_jobs = list(bulk_jobs or [])
        self.datastore = datastore
        self.queries = []

    def _merged_table(self, name):
        table = (self.datastore.tables if self.datastore else {}).get(name)
        rows = {}
        if table:
            for row in table.inserts:
                rows[str(row.get("ROWID"))] = dict(row)
            for update in table.updates:
                row_id = str(update.get("ROWID"))
                if row_id in rows:
                    rows[row_id].update(update)
                else:
                    rows[row_id] = dict(update)
        return list(rows.values())

    def _merged_bulk_jobs(self):
        rows = {str(row.get("ROWID")): dict(row) for row in self.bulk_jobs}
        table = (self.datastore.tables if self.datastore else {}).get("bulk_read_jobs")
        if table:
            for row in table.inserts:
                rows[str(row.get("ROWID"))] = dict(row)
            for update in table.updates:
                row_id = str(update.get("ROWID"))
                if row_id in rows:
                    rows[row_id].update(update)
                else:
                    rows[row_id] = dict(update)
        return list(rows.values())

    def execute_query(self, query):
        self.queries.append(query)
        if re.search(r"from zoho_connections\b", query):
            raise AssertionError(
                "Salesforce worker must not query zoho_connections"
            )
        if "from pipeline_tasks" in query:
            match = re.search(r"task_id = '([^']*)'", query)
            task_id = match.group(1) if match else ""
            row = self.tasks.get(task_id)
            return [{"pipeline_tasks": row}] if row else []
        if "from scan_jobs" in query:
            match = re.search(r"ROWID = (\d+)", query)
            row_id = match.group(1) if match else ""
            row = self.scans.get(row_id)
            return [{"scan_jobs": row}] if row else []
        if "from salesforce_connections" in query:
            match = re.search(r"ROWID = (\d+)", query)
            row_id = match.group(1) if match else ""
            row = self.salesforce_connections.get(row_id)
            return [{"salesforce_connections": row}] if row else []
        if "from scan_module_runs" in query:
            match = re.search(r"scan_row_id = (\d+)", query)
            if match:
                row_id = match.group(1)
                merged = {str(row.get("ROWID")): dict(row) for row in self.modules}
                for row in self._merged_table("scan_module_runs"):
                    merged[str(row.get("ROWID"))] = {
                        **merged.get(str(row.get("ROWID")), {}),
                        **row,
                    }
                return [
                    {"scan_module_runs": row}
                    for row in merged.values()
                    if str(row.get("scan_row_id")) == row_id
                ]
            match = re.search(r"ROWID = (\d+)", query)
            row_id = match.group(1) if match else ""
            merged = {str(row.get("ROWID")): dict(row) for row in self.modules}
            for row in self._merged_table("scan_module_runs"):
                merged[str(row.get("ROWID"))] = {
                    **merged.get(str(row.get("ROWID")), {}),
                    **row,
                }
            row = merged.get(row_id)
            return [{"scan_module_runs": row}] if row else []
        if "from bulk_read_jobs" in query:
            merged = self._merged_bulk_jobs()
            row_match = re.search(r"ROWID = (\d+)", query)
            if row_match:
                row_id = row_match.group(1)
                for row in merged:
                    if str(row.get("ROWID")) == row_id:
                        return [{"bulk_read_jobs": row}]
                return []
            match = re.search(r"scan_module_row_id = (\d+)", query)
            row_id = match.group(1) if match else ""
            return [
                {"bulk_read_jobs": row}
                for row in merged
                if str(row.get("scan_module_row_id")) == row_id
            ]
        if "from processing_batches" in query:
            rows = self._merged_table("processing_batches")
            key_match = re.search(r"batch_key = '([^']*)'", query)
            if key_match:
                key = key_match.group(1)
                for row in rows:
                    if row.get("batch_key") == key:
                        return [{"processing_batches": row}]
                return []
            match = re.search(r"bulk_job_row_id = (\d+)", query)
            row_id = match.group(1) if match else ""
            return [
                {"processing_batches": row}
                for row in rows
                if str(row.get("bulk_job_row_id")) == row_id
            ]
        if "from analytics_results" in query:
            return []
        if "from record_quality_findings" in query:
            rows = self._merged_table("record_quality_findings")
            batch_match = re.search(r"processing_batch_row_id = (\d+)", query)
            if batch_match:
                batch_id = batch_match.group(1)
                rows = [
                    row
                    for row in rows
                    if str(row.get("processing_batch_row_id")) == batch_id
                ]
            limit_match = re.search(r"limit (\d+),(\d+)", query)
            if limit_match:
                offset = int(limit_match.group(1))
                size = int(limit_match.group(2))
                rows = rows[offset : offset + size]
            return [{"record_quality_findings": row} for row in rows]
        if "from zoho_connection_users" in query:
            return []
        if "from salesforce_connection_owners" in query:
            return []
        if "from owner_batch_aggregates" in query:
            return []
        return []


class FakeApp:
    def __init__(self, zcql, datastore=None):
        self._zcql = zcql
        self._datastore = datastore or FakeDatastore()
        zcql.datastore = self._datastore
        self.datastore_called = False
        self._job = FakeJob()
        self._job_scheduling = types.SimpleNamespace(
            job=self._job, cron=None, CRON=None
        )
        self._folder = FakeExportFolder()
        self._bucket = FakeStratusBucket()
        self._filestore = types.SimpleNamespace(folder=lambda _id: self._folder)
        self._stratus = types.SimpleNamespace(bucket=lambda _name: self._bucket)

    def zcql(self):
        return self._zcql

    def datastore(self):
        self.datastore_called = True
        return self._datastore

    def job_scheduling(self):
        return self._job_scheduling

    def filestore(self):
        return self._filestore

    def stratus(self):
        return self._stratus


class FakeJobRequest:
    def __init__(self, params=None):
        self._params = params
        self.get_job_param_calls = []

    def get_all_job_params(self):
        return self._params

    def get_job_param(self, key):
        self.get_job_param_calls.append(key)
        raise AssertionError(
            f"get_job_param({key!r}) must not be called; use get_all_job_params()"
        )


class FakeContext:
    def __init__(self):
        self.closed = None

    def close_with_success(self):
        self.closed = "success"

    def close_with_failure(self):
        self.closed = "failure"


class CapturingHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []
        self.stream = io.StringIO()

    def emit(self, record):
        self.records.append(record)
        self.stream.write(self.format(record))
        self.stream.write("\n")

    def text(self):
        return self.stream.getvalue()


def captured_logs():
    handler = CapturingHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    loggers = [
        worker.logger,
        logging.getLogger("submit_bulk"),
        logging.getLogger("requeue"),
        logging.getLogger("continue_extract"),
    ]
    previous = [(item, item.level) for item in loggers]
    for item in loggers:
        item.addHandler(handler)
        item.setLevel(logging.INFO)
    return loggers, handler, previous


class SalesforceWorkerTaskResolutionTests(unittest.TestCase):
    def _run(
        self,
        job_request,
        zcql=None,
        submit_job=None,
        submit_error=None,
        patch_submit=True,
        poll_job=None,
        poll_error=None,
        patch_poll=True,
        patch_continue=True,
    ):
        context = FakeContext()
        app = FakeApp(zcql or FakeZcql())
        loggers, handler, previous = captured_logs()
        job_payload = {
            "id": "7505g00000AbCdEAAX",
            "state": "UploadComplete",
            "internalStatus": "SUBMITTED",
        }
        try:
            with patch.object(
                worker.zcatalyst_sdk, "initialize", return_value=app
            ) as initialize:
                if not patch_submit:
                    submit_patch = nullcontext()
                elif submit_error is not None:
                    submit_patch = patch(
                        "submit_bulk.submit_salesforce_query_job",
                        side_effect=submit_error,
                    )
                elif submit_job is False:
                    submit_patch = patch(
                        "submit_bulk.submit_salesforce_query_job",
                        side_effect=AssertionError("submit should not be called"),
                    )
                else:
                    submit_patch = patch(
                        "submit_bulk.submit_salesforce_query_job",
                        return_value=submit_job or job_payload,
                    )
                if not patch_poll:
                    poll_patch = nullcontext()
                elif poll_error is not None:
                    poll_patch = patch(
                        "submit_bulk.poll_salesforce_query_job",
                        side_effect=poll_error,
                    )
                elif poll_job is False or poll_job is None:
                    poll_patch = patch(
                        "submit_bulk.poll_salesforce_query_job",
                        side_effect=AssertionError("poll should not be called"),
                    )
                else:
                    poll_patch = patch(
                        "submit_bulk.poll_salesforce_query_job",
                        return_value=poll_job,
                    )
                with submit_patch as submit_mock, poll_patch as poll_mock:
                    if patch_continue:
                        continue_patch = patch.object(
                            worker,
                            "continue_salesforce_extract",
                            return_value=None,
                        )
                    else:
                        continue_patch = nullcontext()
                    with continue_patch:
                        result = worker.handler(job_request, context)
        finally:
            for item, level in previous:
                item.removeHandler(handler)
                item.setLevel(level)
        app.submit_mock = submit_mock
        app.poll_mock = poll_mock
        return result, context, handler, app, initialize

    def test_valid_salesforce_task(self):
        zcql = FakeZcql(
            tasks=[salesforce_task()],
            scans=[salesforce_scan()],
            salesforce_connections=[salesforce_connection()],
            modules=[salesforce_module()],
            zoho_connections=[{"ROWID": CONNECTION_ROW_ID}],
        )
        result, context, handler, app, initialize = self._run(
            FakeJobRequest({"taskId": TASK_ID}),
            zcql,
        )

        self.assertEqual(result["outcome"], "SUBMITTED")
        self.assertEqual(result["taskId"], TASK_ID)
        self.assertEqual(result["scanId"], SCAN_ID)
        self.assertEqual(result["crmProvider"], "salesforce")
        self.assertEqual(result["module"], "Account")
        self.assertEqual(result["providerJobId"], "7505g00000AbCdEAAX")
        self.assertEqual(result["status"], "SUBMITTED")
        self.assertEqual(context.closed, "success")
        self.assertTrue(app.datastore_called)
        initialize.assert_called_once()
        log_text = handler.text()
        self.assertIn(TASK_ID, log_text)
        self.assertIn(SCAN_ID, log_text)
        self.assertIn("crm_provider=salesforce", log_text)
        self.assertIn("Account", log_text)
        self.assertIn("7505g00000AbCdEAAX", log_text)
        self.assertTrue(any("from pipeline_tasks" in query for query in zcql.queries))
        self.assertTrue(
            any("from salesforce_connections" in query for query in zcql.queries)
        )
        self.assertFalse(any("from zoho_connections" in query for query in zcql.queries))
        bulk_updates = app._datastore.tables["bulk_read_jobs"].updates
        self.assertTrue(any(row.get("provider_job_id") == "7505g00000AbCdEAAX" for row in bulk_updates))
        self.assertFalse(any("zoho_job_id" in row for row in bulk_updates))
        self.assertFalse(any("zoho_job_id" in row for row in app._datastore.tables["bulk_read_jobs"].inserts))

    def test_missing_task_id(self):
        result, context, handler, app, initialize = self._run(FakeJobRequest({}))

        self.assertEqual(result["outcome"], "FAILED")
        self.assertEqual(result["code"], "TASK_ID_REQUIRED")
        self.assertEqual(context.closed, "failure")
        initialize.assert_not_called()
        self.assertIn("taskId is required", handler.text())

    def test_nonexistent_task(self):
        result, context, handler, _app, initialize = self._run(
            FakeJobRequest({"taskId": "task_missing"}),
            FakeZcql(),
        )

        self.assertEqual(result["outcome"], "FAILED")
        self.assertEqual(result["code"], "TASK_NOT_FOUND")
        self.assertEqual(context.closed, "failure")
        initialize.assert_called_once()
        self.assertIn("Pipeline task was not found", handler.text())

    def test_wrong_task_type_job_param(self):
        job_request = FakeJobRequest(
            {"taskId": TASK_ID, "taskType": "PROCESS_BATCHES"}
        )
        result, context, handler, _app, initialize = self._run(job_request)

        self.assertEqual(result["outcome"], "FAILED")
        self.assertEqual(result["code"], "WRONG_TASK_TYPE")
        self.assertEqual(context.closed, "failure")
        initialize.assert_not_called()
        self.assertIn("PROCESS_BATCHES", handler.text())
        self.assertEqual(job_request.get_job_param_calls, [])

    def test_zoho_task_rejected(self):
        zcql = FakeZcql(
            tasks=[
                salesforce_task(
                    task_type="ORCHESTRATE_SCAN",
                    task_id="task_zoho_1",
                )
            ],
            scans=[
                salesforce_scan(
                    crm_provider="zoho",
                    scan_id="scan_zoho",
                    connection_row_id="111",
                )
            ],
        )
        result, context, handler, app, _initialize = self._run(
            FakeJobRequest({"taskId": "task_zoho_1"}),
            zcql,
        )

        self.assertEqual(result["outcome"], "FAILED")
        self.assertEqual(result["code"], "WRONG_TASK_TYPE")
        self.assertIn("ORCHESTRATE_SCAN", result["error"])
        self.assertEqual(context.closed, "failure")
        self.assertFalse(app.datastore_called)
        self.assertFalse(any("from scan_jobs" in query for query in zcql.queries))
        self.assertNotIn("scan_zoho", handler.text())

    def test_salesforce_task_with_wrong_provider_rejected(self):
        zcql = FakeZcql(
            tasks=[salesforce_task()],
            scans=[salesforce_scan(crm_provider="zoho")],
            salesforce_connections=[salesforce_connection()],
        )
        result, context, handler, _app, _initialize = self._run(
            FakeJobRequest({"taskId": TASK_ID}),
            zcql,
        )

        self.assertEqual(result["outcome"], "FAILED")
        self.assertEqual(result["code"], "WRONG_CRM_PROVIDER")
        self.assertEqual(context.closed, "failure")
        self.assertFalse(
            any("from salesforce_connections" in query for query in zcql.queries)
        )
        self.assertIn("Salesforce worker requires a Salesforce scan", handler.text())

    def test_missing_scan_rejected(self):
        result, context, _handler, _app, _initialize = self._run(
            FakeJobRequest({"taskId": TASK_ID}),
            FakeZcql(tasks=[salesforce_task()]),
        )

        self.assertEqual(result["outcome"], "FAILED")
        self.assertEqual(result["code"], "SCAN_NOT_FOUND")
        self.assertEqual(context.closed, "failure")

    def test_ownership_mismatch(self):
        zcql = FakeZcql(
            tasks=[salesforce_task()],
            scans=[salesforce_scan()],
            salesforce_connections=[salesforce_connection(ROWID="999")],
        )
        result, context, handler, _app, _initialize = self._run(
            FakeJobRequest({"taskId": TASK_ID}),
            zcql,
        )

        self.assertEqual(result["outcome"], "FAILED")
        self.assertEqual(result["code"], "SCAN_NOT_OWNED")
        self.assertEqual(context.closed, "failure")
        self.assertIn("ownership mismatch", handler.text())

    def test_malformed_parameters_not_object(self):
        job_request = FakeJobRequest(["taskId"])
        result, context, _handler, _app, initialize = self._run(job_request)

        self.assertEqual(result["outcome"], "FAILED")
        self.assertEqual(result["code"], "MALFORMED_PARAMS")
        self.assertEqual(context.closed, "failure")
        initialize.assert_not_called()
        self.assertEqual(job_request.get_job_param_calls, [])

    def test_malformed_task_id_type(self):
        result, context, _handler, _app, initialize = self._run(
            FakeJobRequest({"taskId": ["not-a-string"]})
        )

        self.assertEqual(result["outcome"], "FAILED")
        self.assertEqual(result["code"], "MALFORMED_PARAMS")
        self.assertEqual(context.closed, "failure")
        initialize.assert_not_called()

    def test_no_secret_leakage(self):
        secret = "sf_refresh_token_LIVE_VALUE_do_not_log"
        zcql = FakeZcql(
            tasks=[salesforce_task()],
            scans=[salesforce_scan()],
            salesforce_connections=[salesforce_connection(refresh_token=secret)],
            modules=[salesforce_module()],
        )
        job_request = FakeJobRequest(
            {
                "taskId": TASK_ID,
                "refresh_token": secret,
                "access_token": "sf_access_token_LIVE_VALUE_do_not_log",
                "key": "boilerplate-should-not-be-fetched",
            }
        )
        result, context, handler, app, _initialize = self._run(job_request, zcql)
        log_text = handler.text()

        self.assertEqual(result["outcome"], "SUBMITTED")
        self.assertEqual(context.closed, "success")
        self.assertTrue(app.datastore_called)
        self.assertEqual(job_request.get_job_param_calls, [])
        self.assertNotIn(secret, log_text)
        self.assertNotIn("sf_access_token_LIVE_VALUE_do_not_log", log_text)
        self.assertNotIn("boilerplate-should-not-be-fetched", log_text)
        self.assertNotIn("owner-1", log_text)
        self.assertNotIn("SELECT ", log_text)
        self.assertIn(TASK_ID, log_text)
        self.assertIn(SCAN_ID, log_text)
        self.assertNotIn("access_token", result)
        self.assertNotIn("refresh_token", result)


class SalesforceWorkerSubmitTests(SalesforceWorkerTaskResolutionTests):
    def _ready_zcql(self, modules=None, bulk_jobs=None, **scan_overrides):
        return FakeZcql(
            tasks=[salesforce_task()],
            scans=[salesforce_scan(**scan_overrides)],
            salesforce_connections=[salesforce_connection()],
            modules=modules or [salesforce_module()],
            bulk_jobs=bulk_jobs or [],
        )

    def test_submits_one_bulk_job_through_bulk_query(self):
        result, context, _handler, app, _initialize = self._run(
            FakeJobRequest({"taskId": TASK_ID}),
            self._ready_zcql(),
        )
        self.assertEqual(result["outcome"], "SUBMITTED")
        self.assertEqual(context.closed, "success")
        args, _kwargs = app.submit_mock.call_args
        self.assertEqual(args[2], "Account")
        self.assertIn("Id", args[3])
        self.assertIn("CreatedDate", args[3])
        self.assertIn("LastModifiedDate", args[3])
        self.assertEqual(args[4], "CreatedDate")
        self.assertIsNone(args[8] if len(args) > 8 else _kwargs.get("bulk_row"))

    def test_opportunity_object_name_is_preserved(self):
        result, _context, _handler, app, _initialize = self._run(
            FakeJobRequest({"taskId": TASK_ID}),
            self._ready_zcql(modules=[salesforce_module("Opportunity", "202")]),
        )
        self.assertEqual(result["module"], "Opportunity")
        self.assertEqual(app.submit_mock.call_args[0][2], "Opportunity")
        self.assertNotEqual(app.submit_mock.call_args[0][2], "Deals")

    def test_modified_clock_uses_last_modified_date(self):
        result, _context, _handler, app, _initialize = self._run(
            FakeJobRequest({"taskId": TASK_ID}),
            self._ready_zcql(clock_field="LastModifiedDate"),
        )
        self.assertEqual(result["outcome"], "SUBMITTED")
        self.assertEqual(app.submit_mock.call_args[0][4], "LastModifiedDate")

    def test_existing_provider_job_id_prevents_resubmission(self):
        bulk = {
            "ROWID": "301",
            "scan_module_row_id": "201",
            "status": "SUBMITTED",
            "provider_job_id": LIVE_PROVIDER_JOB_ID,
        }
        result, context, _handler, app, _initialize = self._run(
            FakeJobRequest({"taskId": TASK_ID}),
            self._ready_zcql(bulk_jobs=[bulk]),
            submit_job=False,
            poll_job={
                "id": LIVE_PROVIDER_JOB_ID,
                "state": "InProgress",
                "internalStatus": "PROCESSING",
                "numberRecordsProcessed": 4,
            },
        )
        self.assertEqual(result["outcome"], "POLL_WAITING")
        self.assertEqual(result["providerJobId"], LIVE_PROVIDER_JOB_ID)
        self.assertEqual(context.closed, "success")
        app.submit_mock.assert_not_called()
        app.poll_mock.assert_called_once()

    def test_submitting_status_blocks_duplicate_active_submission(self):
        bulk = {
            "ROWID": "301",
            "scan_module_row_id": "201",
            "status": "SUBMITTING",
        }
        result, context, _handler, app, _initialize = self._run(
            FakeJobRequest({"taskId": TASK_ID}),
            self._ready_zcql(bulk_jobs=[bulk]),
            submit_job=False,
        )
        self.assertEqual(result["outcome"], "RETRY_BLOCKED")
        self.assertEqual(result["status"], "SUBMITTING")
        self.assertEqual(context.closed, "success")
        app.submit_mock.assert_not_called()

    def test_salesforce_api_failure_before_job_create(self):
        result, context, _handler, app, _initialize = self._run(
            FakeJobRequest({"taskId": TASK_ID}),
            self._ready_zcql(),
            submit_error=SalesforceBulkError(
                "INVALID_SOQL", "Salesforce rejected the generated query"
            ),
        )
        self.assertEqual(result["outcome"], "FAILED")
        self.assertEqual(result["code"], "INVALID_SOQL")
        self.assertEqual(context.closed, "failure")
        statuses = [
            row.get("status")
            for row in app._datastore.tables["bulk_read_jobs"].updates
        ]
        self.assertIn("FAILED_TERMINAL", statuses)
        self.assertFalse(
            any(row.get("provider_job_id") for row in app._datastore.tables["bulk_read_jobs"].updates)
        )
        self.assertFalse(
            any("zoho_job_id" in row for row in app._datastore.tables["bulk_read_jobs"].updates)
        )

    def test_ambiguous_api_failure_is_submission_unknown(self):
        result, context, _handler, app, _initialize = self._run(
            FakeJobRequest({"taskId": TASK_ID}),
            self._ready_zcql(),
            submit_error=SalesforceBulkError(
                "SALESFORCE_BULK_QUERY_FAILED",
                "Salesforce Bulk query request failed",
            ),
        )
        self.assertEqual(result["outcome"], "SUBMISSION_UNKNOWN")
        self.assertEqual(context.closed, "success")
        statuses = [
            row.get("status")
            for row in app._datastore.tables["bulk_read_jobs"].updates
        ]
        self.assertIn("SUBMISSION_UNKNOWN", statuses)

    def test_provider_job_id_persist_failure_is_submission_unknown(self):
        zcql = self._ready_zcql()
        app = FakeApp(zcql)
        app._datastore.table("bulk_read_jobs").fail_on = lambda row: (
            row.get("status") == "SUBMITTED" and bool(row.get("provider_job_id"))
        )
        zcql.datastore = app._datastore
        context = FakeContext()
        loggers, handler, previous = captured_logs()
        try:
            with patch.object(worker.zcatalyst_sdk, "initialize", return_value=app):
                with patch(
                    "submit_bulk.submit_salesforce_query_job",
                    return_value={"id": "750PersistFailJobId", "state": "UploadComplete"},
                ):
                    result = worker.handler(FakeJobRequest({"taskId": TASK_ID}), context)
        finally:
            for item, level in previous:
                item.removeHandler(handler)
                item.setLevel(level)
        self.assertEqual(result["outcome"], "SUBMISSION_UNKNOWN")
        self.assertEqual(result["providerJobId"], "750PersistFailJobId")
        self.assertEqual(context.closed, "success")
        retry, retry_context, _handler, retry_app, _init = self._run(
            FakeJobRequest({"taskId": TASK_ID}),
            FakeZcql(
                tasks=[salesforce_task()],
                scans=[salesforce_scan()],
                salesforce_connections=[salesforce_connection()],
                modules=[salesforce_module()],
                bulk_jobs=[
                    {
                        "ROWID": "301",
                        "scan_module_row_id": "201",
                        "status": "SUBMISSION_UNKNOWN",
                        "provider_job_id": "750PersistFailJobId",
                    }
                ],
            ),
            submit_job=False,
            poll_job={
                "id": "750PersistFailJobId",
                "state": "UploadComplete",
                "internalStatus": "SUBMITTED",
                "numberRecordsProcessed": None,
            },
        )
        self.assertEqual(retry["outcome"], "POLL_WAITING")
        self.assertEqual(retry["providerJobId"], "750PersistFailJobId")
        retry_app.submit_mock.assert_not_called()
        retry_app.poll_mock.assert_called_once()
        self.assertEqual(retry_context.closed, "success")

    def test_token_refresh_path_is_used(self):
        response = Mock()
        response.ok = True
        response.status_code = 200
        response.json.return_value = {
            "id": "7505g00000ToknAAA",
            "state": "UploadComplete",
            "object": "Account",
            "operation": "query",
        }
        zcql = self._ready_zcql()
        with patch(
            "salesforce.client.get_salesforce_access_token",
            return_value=("stored-access-token", "https://example.my.salesforce.com"),
        ) as token_refresh, patch(
            "salesforce.bulk_query.requests.post", return_value=response
        ) as posted:
            result, context, handler, app, _initialize = self._run(
                FakeJobRequest({"taskId": TASK_ID}),
                zcql,
                patch_submit=False,
            )
        self.assertEqual(result["outcome"], "SUBMITTED")
        self.assertEqual(result["providerJobId"], "7505g00000ToknAAA")
        token_refresh.assert_called_once()
        posted.assert_called_once()
        self.assertNotIn("access_token", posted.call_args.kwargs.get("json") or {})
        self.assertEqual(context.closed, "success")
        self.assertNotIn("stored-access-token", handler.text())
        self.assertNotIn("SELECT ", handler.text())

    def test_one_module_per_invocation(self):
        result, _context, _handler, app, _initialize = self._run(
            FakeJobRequest({"taskId": TASK_ID}),
            self._ready_zcql(
                modules=[
                    salesforce_module("Account", "201"),
                    salesforce_module("Opportunity", "202"),
                ]
            ),
        )
        self.assertEqual(result["module"], "Account")
        self.assertEqual(app.submit_mock.call_count, 1)
        self.assertEqual(app.submit_mock.call_args[0][2], "Account")

    def test_zoho_path_is_unchanged(self):
        worker_submit = (WORKER_ROOT / "submit_bulk.py").read_text(encoding="utf-8")
        zoho_submit = (
            Path(__file__).resolve().parents[1]
            / "functions"
            / "ai_data_analytics_function"
            / "bulk_read"
            / "submit.py"
        ).read_text(encoding="utf-8")
        zoho_worker = (
            Path(__file__).resolve().parents[1]
            / "functions"
            / "ai_data_analytics_worker"
            / "main.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn('zoho_job_id":', worker_submit)
        self.assertIn("must not write zoho_job_id", worker_submit)
        self.assertNotIn("from bulk_read", worker_submit)
        self.assertNotIn("import bulk_read", worker_submit)
        self.assertIn("zoho_job_id", zoho_submit)
        self.assertIn("ORCHESTRATE_SCAN", zoho_worker)
        self.assertNotIn("ORCHESTRATE_SALESFORCE_SCAN", zoho_worker)
        lease_source = (WORKER_ROOT / "lease.py").read_text(encoding="utf-8")
        self.assertIn("lease_expires_at", lease_source)
        self.assertIn("LEASE_MINUTES = 10", lease_source)
        self.assertIn('"PLANNED", "QUEUED", "PAUSED_RETRYABLE", "OUTCOME_UNKNOWN"', lease_source.replace("\n", " "))


class SalesforceWorkerPollTests(SalesforceWorkerTaskResolutionTests):
    def setUp(self):
        self.env_patch = patch.dict(os.environ, WORKER_ENV, clear=False)
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()

    def _ready_zcql(self, modules=None, bulk_jobs=None, **scan_overrides):
        return FakeZcql(
            tasks=[salesforce_task()],
            scans=[salesforce_scan(**scan_overrides)],
            salesforce_connections=[salesforce_connection()],
            modules=modules or [salesforce_module()],
            bulk_jobs=bulk_jobs or [],
        )

    def _existing_bulk(self, **overrides):
        row = {
            "ROWID": "301",
            "scan_module_row_id": "201",
            "status": "SUBMITTED",
            "provider_job_id": LIVE_PROVIDER_JOB_ID,
        }
        row.update(overrides)
        return row

    def _poll_http(self, payload, bulk=None, status=200):
        response = Mock()
        response.ok = 200 <= status < 300
        response.status_code = status
        response.json.return_value = payload
        zcql = self._ready_zcql(
            bulk_jobs=[bulk or self._existing_bulk()],
            status="EXTRACTING",
        )
        with patch(
            "salesforce.client.get_salesforce_access_token",
            return_value=("stored-access-token", "https://example.my.salesforce.com"),
        ), patch(
            "salesforce.bulk_query.requests.post",
            side_effect=AssertionError("POST /jobs/query must not be called"),
        ) as posted, patch(
            "salesforce.bulk_query.requests.get",
            return_value=response,
        ) as gotten:
            result, context, handler, app, _initialize = self._run(
                FakeJobRequest({"taskId": TASK_ID}),
                zcql,
                patch_submit=False,
                patch_poll=False,
            )
        return result, context, handler, app, posted, gotten

    def test_upload_complete_maps_to_submitted_and_requeues(self):
        result, context, _handler, app, posted, gotten = self._poll_http(
            {
                "id": LIVE_PROVIDER_JOB_ID,
                "state": "UploadComplete",
                "operation": "query",
                "numberRecordsProcessed": 0,
            }
        )
        self.assertEqual(result["outcome"], "POLL_WAITING")
        self.assertEqual(result["status"], "SUBMITTED")
        self.assertEqual(result["providerState"], "UploadComplete")
        self.assertEqual(result["providerJobId"], LIVE_PROVIDER_JOB_ID)
        self.assertTrue(result["requeue"])
        self.assertTrue(result["requeued"])
        self.assertEqual(context.closed, "success")
        posted.assert_not_called()
        gotten.assert_called_once()
        called_url = gotten.call_args.kwargs.get("url") or gotten.call_args.args[0]
        self.assertIn(f"/jobs/query/{LIVE_PROVIDER_JOB_ID}", called_url)
        self.assertNotIn("/results", called_url)
        self.assertEqual(len(app._job.submitted), 1)
        self.assertEqual(app._job.submitted[0]["params"]["taskId"], TASK_ID)
        bulk_updates = app._datastore.tables["bulk_read_jobs"].updates
        self.assertTrue(
            any(row.get("status") == "SUBMITTED" for row in bulk_updates)
        )
        self.assertTrue(any(row.get("next_retry_at") for row in bulk_updates))
        self.assertFalse(any("zoho_job_id" in row for row in bulk_updates))

    def test_in_progress_persists_count_and_requeues_without_busy_loop(self):
        result, context, handler, app, posted, gotten = self._poll_http(
            {
                "id": LIVE_PROVIDER_JOB_ID,
                "state": "InProgress",
                "operation": "query",
                "numberRecordsProcessed": 18,
            }
        )
        self.assertEqual(result["outcome"], "POLL_WAITING")
        self.assertEqual(result["status"], "PROCESSING")
        self.assertEqual(result["providerState"], "InProgress")
        self.assertEqual(result["providerRecordCount"], 18)
        self.assertEqual(result["retryAfterSeconds"], 30)
        self.assertTrue(result["requeued"])
        self.assertEqual(context.closed, "success")
        posted.assert_not_called()
        gotten.assert_called_once()
        called_url = gotten.call_args.kwargs.get("url") or gotten.call_args.args[0]
        self.assertNotIn("/results", called_url)
        bulk_updates = app._datastore.tables["bulk_read_jobs"].updates
        matching = [
            row
            for row in bulk_updates
            if row.get("status") == "PROCESSING"
        ]
        self.assertTrue(matching)
        self.assertEqual(matching[0]["provider_record_count"], 18)
        self.assertEqual(matching[0]["provider_job_id"], LIVE_PROVIDER_JOB_ID)
        self.assertEqual(matching[0]["status"], "PROCESSING")
        self.assertNotIn("provider_status", matching[0])
        self.assertTrue(matching[0].get("next_retry_at"))
        task_updates = app._datastore.tables["pipeline_tasks"].updates
        self.assertTrue(any(row.get("status") == "QUEUED" for row in task_updates))
        self.assertEqual(len(app._job.submitted), 1)
        log_text = handler.text()
        self.assertIn("SALESFORCE_PROVIDER_POLL", log_text)
        self.assertIn("SALESFORCE_PROVIDER_PROCESSING", log_text)
        self.assertIn("SALESFORCE_TASK_REQUEUED", log_text)

    def test_job_complete_stops_at_ready_to_download_without_download(self):
        result, context, handler, app, posted, gotten = self._poll_http(
            {
                "id": LIVE_PROVIDER_JOB_ID,
                "state": "JobComplete",
                "operation": "query",
                "numberRecordsProcessed": 42,
                "numberRecordsFailed": 0,
            }
        )
        self.assertEqual(result["outcome"], "READY_TO_DOWNLOAD")
        self.assertEqual(result["status"], "READY_TO_DOWNLOAD")
        self.assertEqual(result["providerRecordCount"], 42)
        self.assertFalse(result.get("requeue"))
        self.assertNotEqual(result.get("requeued"), True)
        self.assertEqual(context.closed, "success")
        posted.assert_not_called()
        gotten.assert_called_once()
        called_url = gotten.call_args.kwargs.get("url") or gotten.call_args.args[0]
        self.assertIn(f"/jobs/query/{LIVE_PROVIDER_JOB_ID}", called_url)
        self.assertNotIn("/results", called_url)
        self.assertEqual(app._job.submitted, [])
        bulk_updates = app._datastore.tables["bulk_read_jobs"].updates
        matching = [
            row for row in bulk_updates if row.get("status") == "READY_TO_DOWNLOAD"
        ]
        self.assertTrue(matching)
        self.assertEqual(matching[0]["provider_record_count"], 42)
        self.assertEqual(matching[0]["status"], "READY_TO_DOWNLOAD")
        self.assertNotIn("provider_status", matching[0])
        self.assertIn("SALESFORCE_PROVIDER_COMPLETE", handler.text())
        module_updates = app._datastore.tables["scan_module_runs"].updates
        self.assertTrue(
            any(row.get("status") == "READY_TO_DOWNLOAD" for row in module_updates)
        )

    def test_failed_persists_terminal_failure_and_stops(self):
        result, context, handler, app, posted, gotten = self._poll_http(
            {
                "id": LIVE_PROVIDER_JOB_ID,
                "state": "Failed",
                "errorMessage": "InvalidBatch",
            }
        )
        self.assertEqual(result["outcome"], "FAILED_TERMINAL")
        self.assertEqual(result["status"], "FAILED_TERMINAL")
        self.assertEqual(result["providerState"], "Failed")
        self.assertFalse(result.get("requeue"))
        self.assertEqual(context.closed, "success")
        posted.assert_not_called()
        gotten.assert_called_once()
        self.assertEqual(app._job.submitted, [])
        bulk_updates = app._datastore.tables["bulk_read_jobs"].updates
        matching = [
            row for row in bulk_updates if row.get("status") == "FAILED_TERMINAL"
        ]
        self.assertTrue(matching)
        self.assertEqual(matching[0]["controlled_error_code"], "InvalidBatch")
        self.assertEqual(matching[0]["status"], "FAILED_TERMINAL")
        self.assertNotIn("provider_status", matching[0])
        self.assertIn("SALESFORCE_PROVIDER_FAILED", handler.text())
        self.assertEqual(app._job.submitted, [])
        scan_updates = app._datastore.tables["scan_jobs"].updates
        self.assertTrue(
            any(row.get("status") == "PAUSED_RETRYABLE" for row in scan_updates)
        )

    def test_aborted_persists_terminal_failure_and_stops(self):
        result, context, _handler, app, posted, _gotten = self._poll_http(
            {"id": LIVE_PROVIDER_JOB_ID, "state": "Aborted"}
        )
        self.assertEqual(result["outcome"], "FAILED_TERMINAL")
        self.assertEqual(result["providerState"], "Aborted")
        self.assertFalse(result.get("requeue"))
        self.assertEqual(context.closed, "success")
        posted.assert_not_called()
        self.assertEqual(app._job.submitted, [])
        bulk_updates = app._datastore.tables["bulk_read_jobs"].updates
        matching = [
            row for row in bulk_updates if row.get("status") == "FAILED_TERMINAL"
        ]
        self.assertTrue(matching)
        self.assertEqual(
            matching[0]["controlled_error_code"], "SALESFORCE_BULK_JOB_ABORTED"
        )

    def test_existing_provider_job_id_never_posts_a_new_query_job(self):
        result, _context, _handler, app, posted, gotten = self._poll_http(
            {
                "id": LIVE_PROVIDER_JOB_ID,
                "state": "InProgress",
                "numberRecordsProcessed": 1,
            },
            bulk=self._existing_bulk(status="SUBMISSION_UNKNOWN"),
        )
        self.assertEqual(result["outcome"], "POLL_WAITING")
        posted.assert_not_called()
        gotten.assert_called_once()
        called_url = gotten.call_args.kwargs.get("url") or gotten.call_args.args[0]
        self.assertIn("/jobs/query/" + LIVE_PROVIDER_JOB_ID, called_url)

    def test_next_retry_at_skips_salesforce_get_and_requeues(self):
        future = datetime.now(timezone.utc) + timedelta(seconds=20)
        result, context, _handler, app, _initialize = self._run(
            FakeJobRequest({"taskId": TASK_ID}),
            self._ready_zcql(
                bulk_jobs=[
                    self._existing_bulk(
                        status="PROCESSING",
                        next_retry_at=future.strftime("%Y-%m-%d %H:%M:%S"),
                    )
                ],
                status="EXTRACTING",
            ),
            submit_job=False,
            poll_job=False,
        )
        self.assertEqual(result["outcome"], "POLL_WAITING")
        self.assertEqual(result["reason"], "next_retry_at")
        self.assertGreater(result["retryAfterSeconds"], 0)
        self.assertTrue(result["requeued"])
        self.assertEqual(context.closed, "success")
        app.poll_mock.assert_not_called()
        app.submit_mock.assert_not_called()
        self.assertEqual(len(app._job.submitted), 1)

    def test_ready_to_download_does_not_resubmit_or_poll(self):
        result, context, _handler, app, _initialize = self._run(
            FakeJobRequest({"taskId": TASK_ID}),
            self._ready_zcql(
                bulk_jobs=[
                    self._existing_bulk(
                        status="READY_TO_DOWNLOAD",
                        provider_record_count=42,
                    )
                ],
                status="EXTRACTING",
            ),
            submit_job=False,
            poll_job=False,
        )
        self.assertEqual(result["outcome"], "READY_TO_DOWNLOAD")
        self.assertFalse(result.get("requeue"))
        self.assertEqual(context.closed, "success")
        app.submit_mock.assert_not_called()
        app.poll_mock.assert_not_called()
        self.assertEqual(app._job.submitted, [])

    def test_blocked_download_unknown_with_file_releases_planned(self):
        result, context, _handler, app, _initialize = self._run(
            FakeJobRequest({"taskId": TASK_ID}),
            self._ready_zcql(
                bulk_jobs=[
                    self._existing_bulk(
                        status="DOWNLOAD_UNKNOWN",
                        source_file_id="888",
                    )
                ],
                status="EXTRACTING",
            ),
            submit_job=False,
            poll_job=False,
        )
        self.assertEqual(result["outcome"], "RETRY_BLOCKED")
        self.assertFalse(result.get("requeue"))
        self.assertEqual(context.closed, "success")
        app.submit_mock.assert_not_called()
        app.poll_mock.assert_not_called()
        self.assertEqual(app._job.submitted, [])
        statuses = [
            row.get("status")
            for row in app._datastore.tables["pipeline_tasks"].updates
        ]
        self.assertIn("PLANNED", statuses)

    def test_claims_queued_task_to_running_before_salesforce_work(self):
        result, context, handler, app, _initialize = self._run(
            FakeJobRequest({"taskId": TASK_ID}),
            self._ready_zcql(
                bulk_jobs=[self._existing_bulk()],
                status="EXTRACTING",
            ),
            submit_job=False,
            poll_job={
                "id": LIVE_PROVIDER_JOB_ID,
                "state": "InProgress",
                "internalStatus": "PROCESSING",
                "numberRecordsProcessed": 2,
            },
        )
        self.assertEqual(result["outcome"], "POLL_WAITING")
        self.assertEqual(context.closed, "success")
        task_updates = app._datastore.tables["pipeline_tasks"].updates
        self.assertTrue(any(row.get("status") == "RUNNING" for row in task_updates))
        self.assertTrue(any(row.get("lease_expires_at") for row in task_updates))
        self.assertIn("SALESFORCE_TASK_CLAIMED", handler.text())
        self.assertIn("pipeline_task_status=RUNNING", handler.text())

    def test_already_running_valid_lease_skips_salesforce_work(self):
        future = datetime.now(timezone.utc) + timedelta(minutes=10)
        zcql = FakeZcql(
            tasks=[
                salesforce_task(
                    status="RUNNING",
                    lease_expires_at=future.strftime("%Y-%m-%d %H:%M:%S"),
                )
            ],
            scans=[salesforce_scan(status="EXTRACTING")],
            salesforce_connections=[salesforce_connection()],
            modules=[salesforce_module()],
            bulk_jobs=[self._existing_bulk()],
        )
        result, context, handler, app, _initialize = self._run(
            FakeJobRequest({"taskId": TASK_ID}),
            zcql,
            submit_job=False,
            poll_job=False,
        )
        self.assertEqual(result["outcome"], "ALREADY_RUNNING")
        self.assertEqual(context.closed, "success")
        self.assertTrue(app.datastore_called)
        app.submit_mock.assert_not_called()
        app.poll_mock.assert_not_called()
        self.assertEqual(app._job.submitted, [])
        self.assertIn("SALESFORCE_TASK_ALREADY_RUNNING", handler.text())

    def test_expired_running_lease_is_reclaimed_like_zoho_retry(self):
        past = datetime.now(timezone.utc) - timedelta(minutes=11)
        zcql = FakeZcql(
            tasks=[
                salesforce_task(
                    status="RUNNING",
                    lease_expires_at=past.strftime("%Y-%m-%d %H:%M:%S"),
                )
            ],
            scans=[salesforce_scan(status="EXTRACTING")],
            salesforce_connections=[salesforce_connection()],
            modules=[salesforce_module()],
            bulk_jobs=[self._existing_bulk()],
        )
        result, context, handler, app, _initialize = self._run(
            FakeJobRequest({"taskId": TASK_ID}),
            zcql,
            submit_job=False,
            poll_job={
                "id": LIVE_PROVIDER_JOB_ID,
                "state": "InProgress",
                "internalStatus": "PROCESSING",
            },
        )
        self.assertEqual(result["outcome"], "POLL_WAITING")
        self.assertEqual(context.closed, "success")
        self.assertIn("SALESFORCE_TASK_CLAIMED", handler.text())
        app.poll_mock.assert_called_once()
        app.submit_mock.assert_not_called()

    def test_unexpected_crash_after_claim_pauses_retryable(self):
        zcql = self._ready_zcql(bulk_jobs=[self._existing_bulk()], status="EXTRACTING")
        context = FakeContext()
        app = FakeApp(zcql)
        loggers, handler, previous = captured_logs()
        try:
            with patch.object(worker.zcatalyst_sdk, "initialize", return_value=app):
                with patch.object(
                    worker,
                    "submit_one_salesforce_bulk_job",
                    side_effect=RuntimeError("boom"),
                ):
                    result = worker.handler(
                        FakeJobRequest({"taskId": TASK_ID}), context
                    )
        finally:
            for item, level in previous:
                item.removeHandler(handler)
                item.setLevel(level)
        self.assertEqual(result["outcome"], "FAILED")
        self.assertEqual(context.closed, "failure")
        statuses = [
            row.get("status")
            for row in app._datastore.tables["pipeline_tasks"].updates
        ]
        self.assertIn("RUNNING", statuses)
        self.assertIn("PAUSED_RETRYABLE", statuses)

    def test_stuck_task_recovers_with_get_not_post(self):
        stuck_task_id = "task_e73fed9cca52462696e01f7c2e2edf4a"
        stuck_scan_id = "scan_1f09354578c7422c82d8f18d8a161052"
        response = Mock()
        response.ok = True
        response.status_code = 200
        response.json.return_value = {
            "id": LIVE_PROVIDER_JOB_ID,
            "state": "InProgress",
            "operation": "query",
            "numberRecordsProcessed": 7,
        }
        zcql = FakeZcql(
            tasks=[salesforce_task(task_id=stuck_task_id, status="QUEUED")],
            scans=[salesforce_scan(scan_id=stuck_scan_id, status="EXTRACTING")],
            salesforce_connections=[salesforce_connection()],
            modules=[salesforce_module()],
            bulk_jobs=[self._existing_bulk()],
        )
        with patch(
            "salesforce.client.get_salesforce_access_token",
            return_value=("stored-access-token", "https://example.my.salesforce.com"),
        ), patch(
            "salesforce.bulk_query.requests.post",
            side_effect=AssertionError("POST /jobs/query must not be called"),
        ) as posted, patch(
            "salesforce.bulk_query.requests.get",
            return_value=response,
        ) as gotten:
            result, context, handler, app, _initialize = self._run(
                FakeJobRequest({"taskId": stuck_task_id}),
                zcql,
                patch_submit=False,
                patch_poll=False,
            )
        self.assertEqual(result["outcome"], "POLL_WAITING")
        self.assertEqual(result["providerJobId"], LIVE_PROVIDER_JOB_ID)
        self.assertEqual(context.closed, "success")
        posted.assert_not_called()
        gotten.assert_called_once()
        called_url = gotten.call_args.kwargs.get("url") or gotten.call_args.args[0]
        self.assertIn(f"/jobs/query/{LIVE_PROVIDER_JOB_ID}", called_url)
        self.assertNotIn("/results", called_url)
        self.assertIn("SALESFORCE_TASK_CLAIMED", handler.text())
        self.assertIn("SALESFORCE_PROVIDER_POLL", handler.text())
        self.assertIn(stuck_task_id, handler.text())
        self.assertEqual(len(app._datastore.tables.get("pipeline_tasks", FakeTable()).inserts), 0)

    def test_failed_terminal_existing_job_does_not_resubmit(self):
        result, context, _handler, app, _initialize = self._run(
            FakeJobRequest({"taskId": TASK_ID}),
            self._ready_zcql(
                bulk_jobs=[
                    self._existing_bulk(
                        status="FAILED_TERMINAL",
                    )
                ],
                status="EXTRACTING",
            ),
            submit_job=False,
            poll_job=False,
        )
        self.assertIn(result["outcome"], {"WAITING_FOR_DOWNLOAD", "FAILED_TERMINAL"})
        self.assertEqual(context.closed, "success")
        app.submit_mock.assert_not_called()
        app.poll_mock.assert_not_called()
        self.assertEqual(app._job.submitted, [])


ACCOUNT_CSV = (
    "Id,Name,CreatedDate,LastModifiedDate\n"
    "001000000000001AAA,Acme 1,2026-09-10T00:00:00.000Z,2026-09-11T00:00:00.000Z\n"
    "001000000000002AAA,Acme 2,2026-09-10T00:00:00.000Z,2026-09-11T00:00:00.000Z\n"
    "001000000000003AAA,Acme 3,2026-09-10T00:00:00.000Z,2026-09-11T00:00:00.000Z\n"
    "001000000000004AAA,Acme 4,2026-09-10T00:00:00.000Z,2026-09-11T00:00:00.000Z\n"
    "001000000000005AAA,Acme 5,2026-09-10T00:00:00.000Z,2026-09-11T00:00:00.000Z\n"
).encode("utf-8")


def _http_call_url(call):
    return call.kwargs.get("url") or (call.args[0] if call.args else "")


def _bulk_result_get_calls(gotten):
    return [
        call
        for call in gotten.call_args_list
        if "/jobs/query/" in _http_call_url(call) and "/results" in _http_call_url(call)
    ]


class SalesforceWorkerDownloadProcessTests(SalesforceWorkerTaskResolutionTests):
    def setUp(self):
        self.env_patch = patch.dict(
            os.environ,
            {
                **WORKER_ENV,
                "BULK_EXPORT_FOLDER_ID": "12345",
                "STRATUS_BUCKET_NAME": "crm-extracts",
            },
            clear=False,
        )
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()

    def _ready_zcql(self, modules=None, bulk_jobs=None, **scan_overrides):
        return FakeZcql(
            tasks=[salesforce_task()],
            scans=[salesforce_scan(**scan_overrides)],
            salesforce_connections=[salesforce_connection()],
            modules=modules or [salesforce_module()],
            bulk_jobs=bulk_jobs or [],
        )

    def _existing_bulk(self, **overrides):
        row = {
            "ROWID": "301",
            "scan_module_row_id": "201",
            "status": "SUBMITTED",
            "provider_job_id": LIVE_PROVIDER_JOB_ID,
        }
        row.update(overrides)
        return row

    def _csv_get(self, payload=ACCOUNT_CSV):
        response = Mock()
        response.ok = True
        response.status_code = 200
        response.content = payload
        response.headers = {"Content-Type": "text/csv", "Sforce-Locator": "null"}
        response.json.side_effect = ValueError("not json")
        return response

    def test_job_complete_continues_to_download_without_new_query(self):
        poll_response = Mock()
        poll_response.ok = True
        poll_response.status_code = 200
        poll_response.json.return_value = {
            "id": LIVE_PROVIDER_JOB_ID,
            "state": "JobComplete",
            "operation": "query",
            "numberRecordsProcessed": 5,
            "numberRecordsFailed": 0,
        }
        zcql = self._ready_zcql(
            bulk_jobs=[
                self._existing_bulk(
                    status="SUBMITTED",
                    provider_record_count=5,
                    bulk_job_id="bulk_account",
                )
            ],
            status="EXTRACTING",
        )
        def _get(url, *args, **kwargs):
            del args, kwargs
            if "/results" in str(url):
                return self._csv_get()
            return poll_response

        with patch(
            "salesforce.client.get_salesforce_access_token",
            return_value=("stored-access-token", "https://example.my.salesforce.com"),
        ), patch(
            "salesforce.bulk_query.requests.post",
            side_effect=AssertionError("POST /jobs/query must not be called"),
        ) as posted, patch(
            "salesforce.bulk_query.requests.get",
            side_effect=_get,
        ), patch(
            "salesforce.bulk_results.requests.get",
            side_effect=_get,
        ):
            result, context, handler, app, _initialize = self._run(
                FakeJobRequest({"taskId": TASK_ID}),
                zcql,
                patch_submit=False,
                patch_poll=False,
                patch_continue=False,
            )
        self.assertEqual(result.get("outcome"), "COMPLETED", result)
        self.assertEqual(result["recordsProcessed"], 5)
        self.assertEqual(context.closed, "success")
        posted.assert_not_called()
        self.assertIn("SALESFORCE_PROVIDER_COMPLETE", handler.text())
        self.assertIn("SALESFORCE_RESULT_DOWNLOAD", handler.text())

    def test_ready_to_download_gets_results_and_completes_scan(self):
        zcql = self._ready_zcql(
            bulk_jobs=[
                self._existing_bulk(
                    status="READY_TO_DOWNLOAD",
                    provider_record_count=5,
                    bulk_job_id="bulk_account",
                )
            ],
            status="EXTRACTING",
        )
        with patch(
            "salesforce.client.get_salesforce_access_token",
            return_value=("stored-access-token", "https://example.my.salesforce.com"),
        ), patch(
            "salesforce.bulk_query.requests.post",
            side_effect=AssertionError("POST /jobs/query must not be called"),
        ) as posted, patch(
            "salesforce.bulk_results.requests.get",
            return_value=self._csv_get(),
        ) as gotten:
            result, context, handler, app, _initialize = self._run(
                FakeJobRequest({"taskId": TASK_ID}),
                zcql,
                patch_submit=False,
                patch_poll=False,
                patch_continue=False,
            )
        self.assertEqual(result["outcome"], "COMPLETED")
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["recordsProcessed"], 5)
        self.assertEqual(context.closed, "success")
        posted.assert_not_called()
        result_gets = _bulk_result_get_calls(gotten)
        self.assertEqual(len(result_gets), 1)
        called_url = _http_call_url(result_gets[0])
        self.assertIn(f"/jobs/query/{LIVE_PROVIDER_JOB_ID}/results", called_url)
        self.assertNotIn("zoho", called_url)
        module_updates = app._datastore.tables["scan_module_runs"].updates
        self.assertTrue(any(row.get("records_downloaded") == 5 for row in module_updates))
        self.assertTrue(any(row.get("records_processed") == 5 for row in module_updates))
        self.assertTrue(any(row.get("status") == "COMPLETED" for row in module_updates))
        scan_updates = app._datastore.tables["scan_jobs"].updates
        self.assertTrue(any(row.get("status") == "COMPLETED" for row in scan_updates))
        batches = app._datastore.tables["processing_batches"].inserts
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0]["source_record_count"], 5)
        self.assertTrue(
            any(row.get("status") == "SUCCEEDED" for row in app._datastore.tables["pipeline_tasks"].updates)
        )
        self.assertIn("SALESFORCE_RESULT_DOWNLOAD", handler.text())
        self.assertIn("SALESFORCE_RESULT_DOWNLOADED", handler.text())
        self.assertIn("SALESFORCE_PREPARE_BATCHES", handler.text())
        self.assertIn("SALESFORCE_PROCESS_BATCHES", handler.text())
        self.assertIn("SALESFORCE_SCAN_COMPLETED", handler.text())
        get_headers = result_gets[0].kwargs.get("headers") or {}
        self.assertEqual(get_headers.get("Accept"), "text/csv")

    def test_download_failure_is_retryable_and_does_not_post(self):
        response = Mock()
        response.ok = False
        response.status_code = 500
        response.headers = {"Content-Type": "application/json"}
        response.json.return_value = [{"errorCode": "SERVER_ERROR"}]
        zcql = self._ready_zcql(
            bulk_jobs=[
                self._existing_bulk(status="READY_TO_DOWNLOAD", provider_record_count=5)
            ],
            status="EXTRACTING",
        )
        with patch(
            "salesforce.client.get_salesforce_access_token",
            return_value=("stored-access-token", "https://example.my.salesforce.com"),
        ), patch(
            "salesforce.bulk_query.requests.post",
            side_effect=AssertionError("POST /jobs/query must not be called"),
        ) as posted, patch(
            "salesforce.bulk_results.requests.get",
            return_value=response,
        ):
            result, context, _handler, app, _initialize = self._run(
                FakeJobRequest({"taskId": TASK_ID}),
                zcql,
                patch_submit=False,
                patch_poll=False,
                patch_continue=False,
            )
        self.assertEqual(result["outcome"], "DOWNLOAD_RETRYABLE")
        self.assertTrue(result["requeue"])
        self.assertEqual(context.closed, "success")
        posted.assert_not_called()
        statuses = [
            row.get("status")
            for row in app._datastore.tables["bulk_read_jobs"].updates
        ]
        self.assertIn("DOWNLOAD_RETRYABLE", statuses)

    def test_download_retryable_status_retries_get_without_post(self):
        zcql = self._ready_zcql(
            bulk_jobs=[
                self._existing_bulk(
                    status="DOWNLOAD_RETRYABLE",
                    provider_record_count=5,
                    bulk_job_id="bulk_account",
                    download_attempt_count=1,
                )
            ],
            status="EXTRACTING",
        )
        with patch(
            "salesforce.client.get_salesforce_access_token",
            return_value=("stored-access-token", "https://example.my.salesforce.com"),
        ), patch(
            "salesforce.bulk_query.requests.post",
            side_effect=AssertionError("POST /jobs/query must not be called"),
        ) as posted, patch(
            "salesforce.bulk_results.requests.get",
            return_value=self._csv_get(),
        ) as gotten:
            result, context, _handler, app, _initialize = self._run(
                FakeJobRequest({"taskId": TASK_ID}),
                zcql,
                patch_submit=False,
                patch_poll=False,
                patch_continue=False,
            )
        self.assertEqual(result["outcome"], "COMPLETED")
        self.assertEqual(result["recordsProcessed"], 5)
        self.assertEqual(context.closed, "success")
        posted.assert_not_called()
        result_gets = _bulk_result_get_calls(gotten)
        self.assertEqual(len(result_gets), 1)
        called_url = _http_call_url(result_gets[0])
        self.assertIn(f"/jobs/query/{LIVE_PROVIDER_JOB_ID}/results", called_url)
        self.assertTrue(
            any(
                row.get("status") == "COMPLETED"
                for row in app._datastore.tables["scan_jobs"].updates
            )
        )

    def test_download_unknown_without_source_file_retries_upload(self):
        zcql = self._ready_zcql(
            bulk_jobs=[
                self._existing_bulk(
                    status="DOWNLOAD_UNKNOWN",
                    provider_record_count=5,
                    bulk_job_id="bulk_account",
                    download_attempt_count=1,
                    controlled_error_code="FILESTORE_UPLOAD_FAILED",
                )
            ],
            status="EXTRACTING",
        )
        with patch(
            "salesforce.client.get_salesforce_access_token",
            return_value=("stored-access-token", "https://example.my.salesforce.com"),
        ), patch(
            "salesforce.bulk_query.requests.post",
            side_effect=AssertionError("POST /jobs/query must not be called"),
        ) as posted, patch(
            "salesforce.bulk_results.requests.get",
            return_value=self._csv_get(),
        ) as gotten:
            result, context, _handler, app, _initialize = self._run(
                FakeJobRequest({"taskId": TASK_ID}),
                zcql,
                patch_submit=False,
                patch_poll=False,
                patch_continue=False,
            )
        self.assertEqual(result["outcome"], "COMPLETED")
        self.assertEqual(result["recordsProcessed"], 5)
        self.assertEqual(context.closed, "success")
        posted.assert_not_called()
        result_gets = _bulk_result_get_calls(gotten)
        self.assertEqual(len(result_gets), 1)
        self.assertTrue(app._bucket.uploads)
        self.assertFalse(app._folder.uploads)
        extract_uploads = [
            (name, data)
            for name, data, _body_type in app._bucket.uploads
            if str(name).endswith(".csv") or str(name).endswith(".zip")
        ]
        sidecar_uploads = [
            name
            for name, _data, _body_type in app._bucket.uploads
            if str(name).endswith(".jsonl")
        ]
        self.assertTrue(
            extract_uploads
            and all(data == ACCOUNT_CSV for _name, data in extract_uploads)
        )
        self.assertTrue(
            any(str(name).startswith("exports/") for name, _data in extract_uploads)
        )
        self.assertTrue(sidecar_uploads)
        self.assertTrue(
            all("/fix/" in str(name) for name in sidecar_uploads)
        )
        self.assertTrue(
            any(
                row.get("status") == "DOWNLOADED" and row.get("source_file_key")
                for row in app._datastore.tables["bulk_read_jobs"].updates
            )
        )
        self.assertFalse(
            any(
                row.get("source_file_id")
                for row in app._datastore.tables["bulk_read_jobs"].updates
                if row.get("status") == "DOWNLOADED"
            )
        )

    def test_already_downloaded_skips_get_and_processes(self):
        checksum = hashlib.sha256(ACCOUNT_CSV).hexdigest()
        zcql = self._ready_zcql(
            bulk_jobs=[
                self._existing_bulk(
                    status="DOWNLOADED",
                    provider_record_count=5,
                    bulk_job_id="bulk_account",
                    source_file_id="8001",
                    source_file_name="bulk_account.csv",
                    source_file_checksum=checksum,
                    source_file_size=len(ACCOUNT_CSV),
                )
            ],
            status="EXTRACTING",
        )
        context = FakeContext()
        app = FakeApp(zcql)
        app._folder.files["8001"] = ACCOUNT_CSV
        loggers, handler, previous = captured_logs()
        try:
            with patch.object(worker.zcatalyst_sdk, "initialize", return_value=app):
                with patch(
                    "salesforce.bulk_results.requests.get",
                    side_effect=AssertionError("GET results must not be called"),
                ), patch(
                    "salesforce.bulk_query.requests.post",
                    side_effect=AssertionError("POST /jobs/query must not be called"),
                ):
                    result = worker.handler(FakeJobRequest({"taskId": TASK_ID}), context)
        finally:
            for item, level in previous:
                item.removeHandler(handler)
                item.setLevel(level)
        self.assertEqual(result["outcome"], "COMPLETED")
        self.assertEqual(result["recordsProcessed"], 5)
        self.assertEqual(context.closed, "success")
        self.assertEqual(len(app._datastore.tables["processing_batches"].inserts), 1)
        self.assertTrue(
            any(
                row.get("status") == "COMPLETED"
                for row in app._datastore.tables["scan_module_runs"].updates
            )
        )
        self.assertTrue(
            any(
                row.get("status") == "COMPLETED"
                for row in app._datastore.tables["scan_jobs"].updates
            )
        )

    def test_processing_planned_processes_existing_batches_without_get(self):
        checksum = hashlib.sha256(ACCOUNT_CSV).hexdigest()
        zcql = self._ready_zcql(
            bulk_jobs=[
                self._existing_bulk(
                    status="PROCESSING_PLANNED",
                    provider_record_count=5,
                    bulk_job_id="bulk_account",
                    source_file_id="8001",
                    source_file_name="bulk_account.csv",
                    source_file_checksum=checksum,
                    source_file_size=len(ACCOUNT_CSV),
                )
            ],
            status="EXTRACTING",
        )
        context = FakeContext()
        app = FakeApp(zcql)
        app._folder.files["8001"] = ACCOUNT_CSV
        app._datastore.table("processing_batches").insert_row(
            {
                "batch_id": "batch_existing",
                "bulk_job_row_id": "301",
                "batch_key": "existing-batch-key",
                "batch_number": 1,
                "status": "PLANNED",
                "start_record_index": 0,
                "end_record_index": 4,
                "source_record_count": 5,
                "processed_record_count": 0,
                "attempt_count": 0,
            }
        )
        loggers, handler, previous = captured_logs()
        try:
            with patch.object(worker.zcatalyst_sdk, "initialize", return_value=app):
                with patch(
                    "salesforce.bulk_results.requests.get",
                    side_effect=AssertionError("GET results must not be called"),
                ), patch(
                    "salesforce.bulk_query.requests.post",
                    side_effect=AssertionError("POST /jobs/query must not be called"),
                ):
                    result = worker.handler(FakeJobRequest({"taskId": TASK_ID}), context)
        finally:
            for item, level in previous:
                item.removeHandler(handler)
                item.setLevel(level)
        self.assertEqual(result["outcome"], "COMPLETED")
        self.assertEqual(result["recordsProcessed"], 5)
        self.assertEqual(context.closed, "success")
        self.assertEqual(len(app._datastore.tables["processing_batches"].inserts), 1)
        self.assertTrue(
            any(
                row.get("status") == "COMPLETED"
                and row.get("records_processed") == 5
                for row in app._datastore.tables["scan_module_runs"].updates
            )
        )
        self.assertTrue(
            any(
                row.get("status") == "COMPLETED"
                for row in app._datastore.tables["scan_jobs"].updates
            )
        )
        self.assertIn("SALESFORCE_PROCESS_BATCHES", handler.text())
        self.assertNotIn("SALESFORCE_RESULT_DOWNLOAD", handler.text())


if __name__ == "__main__":
    unittest.main()
