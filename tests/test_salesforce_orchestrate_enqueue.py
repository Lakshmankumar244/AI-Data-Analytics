import io
import logging
import re
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
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
    flask.make_response = lambda *args, **kwargs: None
    flask.redirect = lambda *args, **kwargs: None
    sys.modules["flask"] = flask

if "zcatalyst_sdk" not in sys.modules:
    zcatalyst_sdk = types.ModuleType("zcatalyst_sdk")
    zcatalyst_sdk.initialize = lambda: None
    sys.modules["zcatalyst_sdk"] = zcatalyst_sdk

from pipeline.salesforce_orchestrate_enqueue import (
    SALESFORCE_TASK_TYPE,
    enqueue_salesforce_orchestrate_scan,
    queued_is_stale,
    running_is_stale,
    salesforce_orchestrate_task_key,
)


SCAN = {
    "ROWID": "101",
    "scan_id": "scan_sf_abc",
    "crm_provider": "salesforce",
    "connection_row_id": "555",
    "status": "CREATED",
}
WORKER_ENV = {
    "SALESFORCE_WORKER_JOB_POOL_NAME": "sfDataAnalyticsWorkerPool",
    "SALESFORCE_WORKER_FUNCTION_NAME": "ai_data_analytics_salesforce_worker",
}


class FakeTable:
    def __init__(self):
        self.inserts = []
        self.updates = []
        self._next = 1
        self.insert_error = None

    def insert_row(self, row):
        if self.insert_error:
            raise self.insert_error
        stored = dict(row)
        stored.setdefault("ROWID", str(self._next))
        self._next += 1
        self.inserts.append(stored)
        return stored

    def update_row(self, row):
        self.updates.append(dict(row))
        return row


class FakeDatastore:
    def __init__(self):
        self.tables = {"pipeline_tasks": FakeTable()}

    def table(self, name):
        if name not in self.tables:
            self.tables[name] = FakeTable()
        return self.tables[name]


class TaskAwareZcql:
    def __init__(self, datastore):
        self.datastore = datastore
        self.queries = []

    def _merged_tasks(self):
        table = self.datastore.tables.get("pipeline_tasks")
        if not table:
            return []
        rows = {}
        for row in table.inserts:
            rows[str(row.get("ROWID"))] = dict(row)
        for update in table.updates:
            row_id = str(update.get("ROWID"))
            if row_id in rows:
                rows[row_id].update(update)
        return list(rows.values())

    def execute_query(self, query):
        self.queries.append(query)
        if "from zoho_connections" in query:
            raise AssertionError("Salesforce enqueue must not query zoho_connections")
        if "from pipeline_tasks" in query:
            match = re.search(r"task_key = '([^']*)'", query)
            key = match.group(1) if match else ""
            for row in self._merged_tasks():
                if row.get("task_key") == key:
                    return [{"pipeline_tasks": row}]
            return []
        return []


class FakeJob:
    def __init__(self):
        self.submitted = []
        self.error = None

    def submit_job(self, payload):
        if self.error:
            raise self.error
        self.submitted.append(payload)
        return {"id": "catalyst-job-1"}


class FakeApp:
    def __init__(self, zcql, job=None):
        self._zcql = zcql
        self.job = job or FakeJob()

    def zcql(self):
        return self._zcql

    def job_scheduling(self):
        return types.SimpleNamespace(job=self.job)


class CapturingHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.stream = io.StringIO()

    def emit(self, record):
        self.stream.write(self.format(record))
        self.stream.write("\n")

    def text(self):
        return self.stream.getvalue()


class SalesforceOrchestrateEnqueueTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict("os.environ", WORKER_ENV, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)

    def _enqueue(self, scan=None, datastore=None, app=None):
        datastore = datastore or FakeDatastore()
        zcql = TaskAwareZcql(datastore)
        app = app or FakeApp(zcql)
        handler = CapturingHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger = logging.getLogger("pipeline.salesforce_orchestrate_enqueue")
        logger.addHandler(handler)
        previous = logger.level
        logger.setLevel(logging.INFO)
        try:
            result = enqueue_salesforce_orchestrate_scan(
                app, datastore, scan if scan is not None else dict(SCAN)
            )
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous)
        return result, datastore, app, handler

    def test_creates_salesforce_task_and_submits_to_salesforce_pool(self):
        result, datastore, app, handler = self._enqueue()
        task = datastore.tables["pipeline_tasks"].inserts[0]
        payload = app.job.submitted[0]

        self.assertTrue(result["ok"])
        self.assertTrue(result["submitted"])
        self.assertEqual(task["task_type"], SALESFORCE_TASK_TYPE)
        self.assertEqual(task["scan_row_id"], "101")
        self.assertEqual(task["status"], "PLANNED")
        self.assertEqual(result["task"]["status"], "QUEUED")
        self.assertEqual(payload["jobpool_name"], "sfDataAnalyticsWorkerPool")
        self.assertEqual(payload["target_type"], "Function")
        self.assertEqual(payload["target_name"], "ai_data_analytics_salesforce_worker")
        self.assertEqual(payload["params"], {"taskId": task["task_id"]})
        self.assertNotIn("job_config", payload)
        self.assertNotEqual(payload["params"]["taskId"], task["ROWID"])
        log_text = handler.text()
        self.assertIn(task["task_id"], log_text)
        self.assertIn("scan_sf_abc", log_text)
        self.assertIn("crm_provider=salesforce", log_text)
        self.assertIn("sfDataAnalyticsWorkerPool", log_text)
        self.assertIn("ai_data_analytics_salesforce_worker", log_text)

    def test_does_not_submit_zoho_orchestrate_scan_or_zoho_pool(self):
        result, datastore, app, _handler = self._enqueue()
        source = (
            Path(FUNCTION_ROOT)
            / "pipeline"
            / "salesforce_orchestrate_enqueue.py"
        ).read_text(encoding="utf-8")
        payload = app.job.submitted[0]
        self.assertTrue(result["ok"])
        self.assertEqual(datastore.tables["pipeline_tasks"].inserts[0]["task_type"], SALESFORCE_TASK_TYPE)
        self.assertNotEqual(payload["jobpool_name"], "aiDataAnalyticsWorkerPool")
        self.assertNotEqual(payload["target_name"], "ai_data_analytics_worker")
        self.assertNotIn("ORCHESTRATE_SCAN", payload["params"])
        self.assertNotIn("ANALYTICS_WORKER_JOB_POOL_NAME", source)
        self.assertNotIn("ANALYTICS_WORKER_FUNCTION_NAME", source)
        self.assertNotIn("aiDataAnalyticsWorkerPool", source)
        self.assertNotIn("ai_data_analytics_worker", source)
        zoho = (
            Path(FUNCTION_ROOT) / "pipeline" / "orchestrate_enqueue.py"
        ).read_text(encoding="utf-8")
        self.assertIn('ORCHESTRATE_TASK_TYPE = "ORCHESTRATE_SCAN"', zoho)
        self.assertIn("ANALYTICS_WORKER_JOB_POOL_NAME", zoho)
        self.assertNotIn("SALESFORCE_WORKER_JOB_POOL_NAME", zoho)

    def test_duplicate_enqueue_is_prevented(self):
        datastore = FakeDatastore()
        zcql = TaskAwareZcql(datastore)
        app = FakeApp(zcql)
        first, _, _, _ = self._enqueue(datastore=datastore, app=app)
        handler = CapturingHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger = logging.getLogger("pipeline.salesforce_orchestrate_enqueue")
        logger.addHandler(handler)
        previous = logger.level
        logger.setLevel(logging.INFO)
        try:
            second = enqueue_salesforce_orchestrate_scan(app, datastore, dict(SCAN))
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous)
        self.assertTrue(first["ok"])
        self.assertTrue(first["submitted"])
        self.assertTrue(second["ok"])
        self.assertTrue(second["alreadyActive"])
        self.assertFalse(second["submitted"])
        self.assertEqual(len(datastore.tables["pipeline_tasks"].inserts), 1)
        self.assertEqual(len(app.job.submitted), 1)
        self.assertIn("SALESFORCE_WORKER_ALREADY_ACTIVE", handler.text())
        self.assertIn("queued_startup_grace", handler.text())
        self.assertIn("QUEUED", handler.text())

    def test_zoho_scan_is_rejected(self):
        result, datastore, app, _handler = self._enqueue(
            scan={"ROWID": "9", "scan_id": "scan_zoho", "status": "CREATED"}
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "WRONG_CRM_PROVIDER")
        self.assertEqual(datastore.tables["pipeline_tasks"].inserts, [])
        self.assertEqual(app.job.submitted, [])

    def test_task_create_failure(self):
        datastore = FakeDatastore()
        datastore.tables["pipeline_tasks"].insert_error = RuntimeError("datastore down")
        result, _, app, _handler = self._enqueue(datastore=datastore)
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "SALESFORCE_WORKER_TASK_CREATE_FAILED")
        self.assertEqual(app.job.submitted, [])

    def test_job_submission_4xx_is_paused_retryable(self):
        error = RuntimeError("rejected")
        error.status_code = 400
        job = FakeJob()
        job.error = error
        datastore = FakeDatastore()
        result, datastore, app, _handler = self._enqueue(
            datastore=datastore, app=FakeApp(TaskAwareZcql(datastore), job=job)
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "WORKER_ENQUEUE_REJECTED")
        statuses = [row["status"] for row in datastore.tables["pipeline_tasks"].updates]
        self.assertIn("PAUSED_RETRYABLE", statuses)
        self.assertEqual(app.job.submitted, [])

    def test_job_submission_unknown_failure_preserves_outcome_unknown(self):
        job = FakeJob()
        job.error = RuntimeError("timeout")
        datastore = FakeDatastore()
        result, datastore, app, _handler = self._enqueue(
            datastore=datastore, app=FakeApp(TaskAwareZcql(datastore), job=job)
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "WORKER_ENQUEUE_OUTCOME_UNKNOWN")
        statuses = [row["status"] for row in datastore.tables["pipeline_tasks"].updates]
        self.assertIn("OUTCOME_UNKNOWN", statuses)
        retry = enqueue_salesforce_orchestrate_scan(app, datastore, dict(SCAN))
        self.assertFalse(retry["ok"])
        self.assertEqual(retry["code"], "WORKER_ENQUEUE_OUTCOME_UNKNOWN")
        self.assertEqual(app.job.submitted, [])

    def test_no_secret_leakage(self):
        secret = "sf_refresh_token_LIVE_VALUE_do_not_log"
        scan = {
            **SCAN,
            "access_token": "sf_access_token_LIVE_VALUE_do_not_log",
            "refresh_token": secret,
        }
        result, datastore, app, handler = self._enqueue(scan=scan)
        payload = app.job.submitted[0]
        log_text = handler.text()
        serialized = str(payload)
        self.assertTrue(result["ok"])
        self.assertNotIn(secret, log_text)
        self.assertNotIn("sf_access_token_LIVE_VALUE_do_not_log", log_text)
        self.assertNotIn(secret, serialized)
        self.assertNotIn("sf_access_token_LIVE_VALUE_do_not_log", serialized)
        self.assertEqual(list(payload["params"].keys()), ["taskId"])

    def _seed_task(self, datastore, **fields):
        table = datastore.table("pipeline_tasks")
        row = {
            "ROWID": "9001",
            "task_id": "task_sf_existing",
            "task_key": salesforce_orchestrate_task_key(SCAN["scan_id"]),
            "scan_row_id": SCAN["ROWID"],
            "task_type": SALESFORCE_TASK_TYPE,
            "status": "QUEUED",
            "attempt_count": 1,
        }
        row.update(fields)
        table.inserts.append(row)
        return row

    def test_planned_task_submits_catalyst_job(self):
        result, datastore, app, handler = self._enqueue()
        self.assertTrue(result["submitted"])
        self.assertEqual(result["task"]["status"], "QUEUED")
        self.assertEqual(app.job.submitted[0]["params"]["taskId"], result["task"]["task_id"])
        self.assertIn("SALESFORCE_WORKER_SUBMITTED", handler.text())

    def test_recent_queued_task_is_not_duplicated(self):
        datastore = FakeDatastore()
        recent = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        seeded = self._seed_task(datastore, enqueued_at=recent)
        result, datastore, app, handler = self._enqueue(datastore=datastore)
        self.assertTrue(result["alreadyActive"])
        self.assertFalse(result["submitted"])
        self.assertEqual(app.job.submitted, [])
        self.assertEqual(len(datastore.tables["pipeline_tasks"].inserts), 1)
        self.assertEqual(result["task"]["task_id"], seeded["task_id"])
        self.assertIn("queued_startup_grace", handler.text())

    def test_stale_queued_task_resubmits_same_task_id(self):
        datastore = FakeDatastore()
        stale = (datetime.now(timezone.utc) - timedelta(minutes=20)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        seeded = self._seed_task(datastore, enqueued_at=stale)
        result, datastore, app, handler = self._enqueue(datastore=datastore)
        self.assertTrue(result["ok"])
        self.assertTrue(result["submitted"])
        self.assertTrue(result["staleRecovery"])
        self.assertEqual(len(datastore.tables["pipeline_tasks"].inserts), 1)
        self.assertEqual(app.job.submitted[0]["params"]["taskId"], seeded["task_id"])
        self.assertIn("SALESFORCE_STALE_QUEUED_RECOVERY", handler.text())
        self.assertIn("SALESFORCE_WORKER_SUBMITTED", handler.text())

    def test_running_task_with_valid_lease_is_not_duplicated(self):
        datastore = FakeDatastore()
        future = (datetime.now(timezone.utc) + timedelta(minutes=8)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        seeded = self._seed_task(
            datastore, status="RUNNING", lease_expires_at=future
        )
        result, datastore, app, handler = self._enqueue(datastore=datastore)
        self.assertTrue(result["alreadyActive"])
        self.assertFalse(result["submitted"])
        self.assertFalse(result["submitJobCalled"])
        self.assertEqual(result["reason"], "running")
        self.assertFalse(result["diagnostics"]["runningIsStale"])
        self.assertEqual(app.job.submitted, [])
        self.assertEqual(result["task"]["task_id"], seeded["task_id"])
        self.assertIn("running", handler.text())
        self.assertIn("SALESFORCE_ADVANCE_ENQUEUE_DECISION", handler.text())
        self.assertIn("submit_job_called=false", handler.text())
        self.assertNotIn("SALESFORCE_SUBMIT_JOB_ATTEMPT", handler.text())
        self.assertFalse(running_is_stale(seeded))

    def test_stale_running_task_resubmits_same_task_id(self):
        datastore = FakeDatastore()
        past = (datetime.now(timezone.utc) - timedelta(minutes=20)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        seeded = self._seed_task(
            datastore, status="RUNNING", lease_expires_at=past
        )
        result, datastore, app, handler = self._enqueue(datastore=datastore)
        self.assertTrue(result["ok"])
        self.assertTrue(result["submitted"])
        self.assertTrue(result["staleRecovery"])
        self.assertFalse(result.get("alreadyActive"))
        self.assertEqual(len(datastore.tables["pipeline_tasks"].inserts), 1)
        self.assertEqual(app.job.submitted[0]["params"]["taskId"], seeded["task_id"])
        self.assertIn("SALESFORCE_STALE_RUNNING_RECOVERY", handler.text())
        self.assertIn("SALESFORCE_SUBMIT_JOB_ATTEMPT", handler.text())
        self.assertIn("SALESFORCE_WORKER_SUBMITTED", handler.text())
        self.assertTrue(result["submitJobCalled"])
        self.assertTrue(running_is_stale(seeded))

    def test_running_without_lease_is_stale(self):
        datastore = FakeDatastore()
        seeded = self._seed_task(datastore, status="RUNNING")
        result, datastore, app, handler = self._enqueue(datastore=datastore)
        self.assertTrue(result["submitted"])
        self.assertTrue(result["staleRecovery"])
        self.assertEqual(app.job.submitted[0]["params"]["taskId"], seeded["task_id"])
        self.assertIn("SALESFORCE_STALE_RUNNING_RECOVERY", handler.text())

    def test_download_unknown_scan_recovers_existing_task(self):
        scan = {
            "ROWID": "48465000000182001",
            "scan_id": "scan_1f09354578c7422c82d8f18d8a161052",
            "crm_provider": "salesforce",
            "status": "EXTRACTING",
        }
        datastore = FakeDatastore()
        past = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        datastore.table("pipeline_tasks").inserts.append(
            {
                "ROWID": "9009",
                "task_id": "task_e73fed9cca52462696e01f7c2e2edf4a",
                "task_key": salesforce_orchestrate_task_key(scan["scan_id"]),
                "scan_row_id": scan["ROWID"],
                "task_type": SALESFORCE_TASK_TYPE,
                "status": "RUNNING",
                "lease_expires_at": past,
                "attempt_count": 3,
            }
        )
        result, datastore, app, handler = self._enqueue(scan=scan, datastore=datastore)
        self.assertTrue(result["staleRecovery"])
        self.assertTrue(result["submitted"])
        self.assertEqual(
            app.job.submitted[0]["params"]["taskId"],
            "task_e73fed9cca52462696e01f7c2e2edf4a",
        )
        self.assertEqual(len(datastore.tables["pipeline_tasks"].inserts), 1)
        self.assertIn("SALESFORCE_STALE_RUNNING_RECOVERY", handler.text())

    def test_stuck_scan_recovers_without_second_pipeline_task(self):
        scan = {
            "ROWID": "48465000000182001",
            "scan_id": "scan_1f09354578c7422c82d8f18d8a161052",
            "crm_provider": "salesforce",
            "status": "CREATED",
        }
        datastore = FakeDatastore()
        stale = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        datastore.table("pipeline_tasks").inserts.append(
            {
                "ROWID": "9009",
                "task_id": "task_e73fed9cca52462696e01f7c2e2edf4a",
                "task_key": salesforce_orchestrate_task_key(scan["scan_id"]),
                "scan_row_id": scan["ROWID"],
                "task_type": SALESFORCE_TASK_TYPE,
                "status": "QUEUED",
                "enqueued_at": stale,
                "attempt_count": 1,
            }
        )
        result, datastore, app, handler = self._enqueue(scan=scan, datastore=datastore)
        self.assertTrue(result["staleRecovery"])
        self.assertEqual(
            app.job.submitted[0]["params"]["taskId"],
            "task_e73fed9cca52462696e01f7c2e2edf4a",
        )
        self.assertEqual(len(datastore.tables["pipeline_tasks"].inserts), 1)
        self.assertIn("SALESFORCE_STALE_QUEUED_RECOVERY", handler.text())
        self.assertTrue(queued_is_stale({"status": "QUEUED", "enqueued_at": stale}))


if __name__ == "__main__":
    unittest.main()
