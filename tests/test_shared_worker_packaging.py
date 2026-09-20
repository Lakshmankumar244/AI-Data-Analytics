import hashlib
import importlib.util
import json
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS_ROOT = ROOT / "functions"
SHARED_SOURCE = FUNCTIONS_ROOT / "_shared" / "worker"
SHARED_SALESFORCE = FUNCTIONS_ROOT / "_shared" / "salesforce"
SHARED_ZOHO_ROOT = FUNCTIONS_ROOT / "_shared"
ZOHO_WORKER = FUNCTIONS_ROOT / "ai_data_analytics_worker"
SF_WORKER = FUNCTIONS_ROOT / "ai_data_analytics_salesforce_worker"
HTTP_FUNCTION = FUNCTIONS_ROOT / "ai_data_analytics_function"
CATALYST_JSON = ROOT / "catalyst.json"

SHARED_FILES = (
    "__init__.py",
    "datastore.py",
    "profiler.py",
    "prepare_batches.py",
)
SHARED_SALESFORCE_FILES = (
    "client.py",
    "describe.py",
    "bulk_query.py",
    "bulk_results.py",
    "owner_resolution.py",
)
SHARED_ZOHO_FILES = (
    ("zoho", ("client.py", "user_directory.py")),
    (
        "bulk_read",
        (
            "prepare.py",
            "submit.py",
            "status.py",
            "download.py",
            "request_builder.py",
        ),
    ),
    ("connections", ("token.py", "access.py")),
    ("orchestration", ("choose.py",)),
    ("common", ("profiler.py",)),
)


def _assert_entrypoint_imports_shared(worker_root):
    script = r"""
import importlib.util
import sys
import types
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
if "flask" not in sys.modules:
    flask = types.ModuleType("flask")
    flask.Request = type("Request", (), {})
    flask.make_response = lambda *args, **kwargs: None
    flask.redirect = lambda *args, **kwargs: None
    sys.modules["flask"] = flask
if "zcatalyst_sdk" not in sys.modules:
    stub = types.ModuleType("zcatalyst_sdk")
    stub.initialize = lambda: None
    sys.modules["zcatalyst_sdk"] = stub
spec = importlib.util.spec_from_file_location("worker_entrypoint", root / "main.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
assert callable(module.handler)
assert "shared.prepare_batches" in sys.modules
assert "shared.profiler" in sys.modules
assert "shared.datastore" in sys.modules
assert callable(sys.modules["shared.prepare_batches"].prepare_batches)
print("ok")
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(worker_root)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"entrypoint import failed for {worker_root.name}:\n"
            f"{result.stdout}\n{result.stderr}"
        )
    if "ok" not in result.stdout:
        raise AssertionError(result.stdout + result.stderr)


def _load_module(unique_name, path):
    spec = importlib.util.spec_from_file_location(unique_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SharedWorkerHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.datastore = _load_module(
            "shared_source_datastore",
            SHARED_SOURCE / "datastore.py",
        )

    def test_nested_catalyst_rowid(self):
        self.assertEqual(
            self.datastore.foreign_row_id({"ROWID": "48465000000182004"}),
            "48465000000182004",
        )
        self.assertEqual(
            self.datastore.foreign_row_id({"rowid": "99"}),
            "99",
        )
        self.assertEqual(self.datastore.foreign_row_id("123"), "123")

    def test_numeric_row_id_rejects_non_digits(self):
        with self.assertRaises(ValueError):
            self.datastore.numeric_row_id({"ROWID": "abc"}, "Bulk job link")

    def test_canonical_hash(self):
        encoded = json.dumps(
            {"b": 2, "a": 1},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        self.assertEqual(
            self.datastore.canonical_hash({"b": 2, "a": 1}),
            hashlib.sha256(encoded).hexdigest(),
        )

    def test_catalyst_datetime(self):
        value = datetime(2026, 9, 20, 3, 44, 11, tzinfo=timezone.utc)
        self.assertEqual(
            self.datastore.catalyst_datetime(value),
            "2026-09-20 03:44:11",
        )

    def test_query_one_returns_named_table_row(self):
        zcql = Mock()
        zcql.execute_query.return_value = [{"pipeline_tasks": {"task_id": "task_1"}}]
        row = self.datastore.query_one(
            zcql, "select * from pipeline_tasks limit 1", "pipeline_tasks"
        )
        self.assertEqual(row["task_id"], "task_1")
        self.assertIsNone(
            self.datastore.query_one(Mock(execute_query=Mock(return_value=[])), "q", "t")
        )

    def test_insert_rows_in_chunks(self):
        table = Mock()
        rows = [{"n": i} for i in range(250)]
        self.datastore.insert_rows_in_chunks(table, rows, chunk_size=100)
        self.assertEqual(table.insert_rows.call_count, 3)
        self.assertEqual(len(table.insert_rows.call_args_list[0].args[0]), 100)
        self.assertEqual(len(table.insert_rows.call_args_list[2].args[0]), 50)


class SharedWorkerPackagingTests(unittest.TestCase):
    def test_catalyst_targets_do_not_deploy_shared_source(self):
        config = json.loads(CATALYST_JSON.read_text(encoding="utf-8"))
        self.assertEqual(
            config["functions"]["targets"],
            [
                "ai_data_analytics_function",
                "ai_data_analytics_worker",
                "ai_data_analytics_salesforce_worker",
            ],
        )
        self.assertNotIn("_shared", config["functions"]["targets"])
        self.assertEqual(
            config["functions"]["scripts"]["predeploy"],
            "python _shared/sync_into_workers.py",
        )
        self.assertFalse((SHARED_SOURCE.parent / "catalyst-config.json").exists())

    def test_packaged_copies_match_shared_source(self):
        for worker in (ZOHO_WORKER, SF_WORKER):
            packaged = worker / "shared"
            for name in SHARED_FILES:
                source = (SHARED_SOURCE / name).read_bytes()
                copy = (packaged / name).read_bytes()
                self.assertEqual(source, copy, f"{worker.name}/shared/{name}")

    def test_each_worker_zip_root_contains_shared_package(self):
        for worker in (ZOHO_WORKER, SF_WORKER):
            self.assertTrue((worker / "shared" / "prepare_batches.py").is_file())
            self.assertTrue((worker / "shared" / "profiler.py").is_file())
            self.assertTrue((worker / "shared" / "datastore.py").is_file())
            self.assertTrue((worker / "main.py").is_file())
            self.assertTrue((worker / "catalyst-config.json").is_file())

    def test_zoho_entrypoint_imports_shared_modules(self):
        _assert_entrypoint_imports_shared(ZOHO_WORKER)

    def test_salesforce_entrypoint_imports_shared_modules(self):
        _assert_entrypoint_imports_shared(SF_WORKER)


def _assert_salesforce_modules_import(function_root):
    script = r"""
import importlib
import sys
import types
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
if "flask" not in sys.modules:
    flask = types.ModuleType("flask")
    flask.Request = type("Request", (), {})
    flask.make_response = lambda *args, **kwargs: None
    flask.redirect = lambda *args, **kwargs: None
    sys.modules["flask"] = flask
if "zcatalyst_sdk" not in sys.modules:
    stub = types.ModuleType("zcatalyst_sdk")
    stub.initialize = lambda: None
    sys.modules["zcatalyst_sdk"] = stub
for name in (
    "salesforce.client",
    "salesforce.describe",
    "salesforce.bulk_query",
    "salesforce.bulk_results",
    "salesforce.owner_resolution",
):
    module = importlib.import_module(name)
    assert module is sys.modules[name]
print("ok")
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(function_root)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"Salesforce import failed for {function_root.name}:\n"
            f"{result.stdout}\n{result.stderr}"
        )
    if "ok" not in result.stdout:
        raise AssertionError(result.stdout + result.stderr)


class SharedSalesforcePackagingTests(unittest.TestCase):
    def test_packaged_salesforce_modules_match_shared_source(self):
        for dest in (
            HTTP_FUNCTION / "salesforce",
            SF_WORKER / "salesforce",
        ):
            for name in SHARED_SALESFORCE_FILES:
                source = (SHARED_SALESFORCE / name).read_bytes()
                copy = (dest / name).read_bytes()
                self.assertEqual(source, copy, f"{dest}/{name}")

    def test_zoho_worker_does_not_receive_salesforce_shared_modules(self):
        self.assertFalse((ZOHO_WORKER / "salesforce").exists())
        for name in SHARED_SALESFORCE_FILES:
            self.assertFalse((ZOHO_WORKER / name).exists())
            self.assertFalse((ZOHO_WORKER / "shared" / name).exists())

    def test_user_directory_and_oauth_are_not_in_shared_salesforce(self):
        self.assertFalse((SHARED_SALESFORCE / "user_directory.py").exists())
        self.assertFalse((SHARED_SALESFORCE / "oauth.py").exists())
        self.assertTrue((HTTP_FUNCTION / "salesforce" / "user_directory.py").is_file())
        self.assertTrue((HTTP_FUNCTION / "salesforce" / "oauth.py").is_file())
        self.assertTrue((SF_WORKER / "salesforce" / "user_directory.py").is_file())
        self.assertFalse((SF_WORKER / "salesforce" / "oauth.py").exists())

    def test_client_uses_worker_safe_discovery_error_fallback(self):
        source = (SHARED_SALESFORCE / "client.py").read_text(encoding="utf-8")
        self.assertIn("except ImportError:", source)
        self.assertIn("from common.core import DiscoveryError", source)

    def test_http_function_imports_shared_salesforce_modules(self):
        _assert_salesforce_modules_import(HTTP_FUNCTION)

    def test_salesforce_worker_imports_shared_salesforce_modules(self):
        _assert_salesforce_modules_import(SF_WORKER)


def _assert_zoho_modules_import(function_root):
    script = r"""
import importlib
import sys
import types
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
if "flask" not in sys.modules:
    flask = types.ModuleType("flask")
    flask.Request = type("Request", (), {})
    flask.make_response = lambda *args, **kwargs: None
    flask.redirect = lambda *args, **kwargs: None
    sys.modules["flask"] = flask
if "zcatalyst_sdk" not in sys.modules:
    stub = types.ModuleType("zcatalyst_sdk")
    stub.initialize = lambda: None
    sys.modules["zcatalyst_sdk"] = stub
for name in (
    "zoho.client",
    "zoho.user_directory",
    "bulk_read.prepare",
    "bulk_read.submit",
    "bulk_read.status",
    "bulk_read.download",
    "bulk_read.request_builder",
    "connections.token",
    "connections.access",
    "orchestration.choose",
    "common.profiler",
):
    module = importlib.import_module(name)
    assert module is sys.modules[name]
print("ok")
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(function_root)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"Zoho shared import failed for {function_root.name}:\n"
            f"{result.stdout}\n{result.stderr}"
        )
    if "ok" not in result.stdout:
        raise AssertionError(result.stdout + result.stderr)


class SharedZohoPackagingTests(unittest.TestCase):
    def test_packaged_zoho_modules_match_shared_source(self):
        for dest in (HTTP_FUNCTION, ZOHO_WORKER):
            for package, names in SHARED_ZOHO_FILES:
                for name in names:
                    source = (SHARED_ZOHO_ROOT / package / name).read_bytes()
                    copy = (dest / package / name).read_bytes()
                    self.assertEqual(source, copy, f"{dest.name}/{package}/{name}")

    def test_salesforce_worker_does_not_receive_zoho_shared_modules(self):
        for package, names in SHARED_ZOHO_FILES:
            for name in names:
                self.assertFalse((SF_WORKER / package / name).exists())
                self.assertFalse((SF_WORKER / "shared" / package / name).exists())
                self.assertFalse((SF_WORKER / name).exists())

    def test_shared_zoho_init_files_are_not_copied_into_deploy_trees(self):
        http_zoho_init = (HTTP_FUNCTION / "zoho" / "__init__.py").read_text(
            encoding="utf-8"
        )
        shared_zoho_init = (SHARED_ZOHO_ROOT / "zoho" / "__init__.py").read_text(
            encoding="utf-8"
        )
        self.assertNotEqual(http_zoho_init, shared_zoho_init)
        self.assertFalse((SF_WORKER / "zoho").exists())
        self.assertFalse((SF_WORKER / "bulk_read").exists())

    def test_http_function_imports_shared_zoho_modules(self):
        _assert_zoho_modules_import(HTTP_FUNCTION)

    def test_zoho_worker_imports_shared_zoho_modules(self):
        _assert_zoho_modules_import(ZOHO_WORKER)


if __name__ == "__main__":
    unittest.main()
