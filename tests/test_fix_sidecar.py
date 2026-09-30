import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS_ROOT = ROOT / "functions"
SHARED_ROOT = FUNCTIONS_ROOT / "_shared"
ZOHO_WORKER = FUNCTIONS_ROOT / "ai_data_analytics_worker"
SF_WORKER = FUNCTIONS_ROOT / "ai_data_analytics_salesforce_worker"

if "zcatalyst_sdk" not in sys.modules:
    stub = types.ModuleType("zcatalyst_sdk")
    stub.initialize = lambda: None
    sys.modules["zcatalyst_sdk"] = stub

sys.path.insert(0, str(SHARED_ROOT))
sys.path.insert(0, str(ZOHO_WORKER))

from shared.fix_sidecar import (  # noqa: E402
    attach_sidecar_line,
    build_sidecar_line,
    compact_issue_type_keys,
    encode_fix_jsonl,
    write_fix_sidecar,
)
from storage.extract_store import build_fix_object_key  # noqa: E402


class FakeBucket:
    def __init__(self):
        self.uploads = []
        self.objects = {}

    def put_object(self, key, body, options=None):
        if options and options.get("extract_upload"):
            raise AssertionError("extract_upload must not be used")
        data = body.read() if hasattr(body, "read") else body
        self.uploads.append((key, data))
        self.objects[key] = data
        return True


class FakeApp:
    def __init__(self):
        self._bucket = FakeBucket()

    def stratus(self):
        return types.SimpleNamespace(bucket=lambda _name: self._bucket)


class FakeTable:
    def __init__(self):
        self.inserts = []
        self.deleted = []
        self._next = 1

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
        self.deleted.extend(list(row_ids))
        self.inserts = [
            row for row in self.inserts if str(row.get("ROWID")) not in ids
        ]
        return list(row_ids)


class FakeDatastore:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        if name not in self.tables:
            self.tables[name] = FakeTable()
        return self.tables[name]


class FakeZcql:
    def __init__(self, datastore):
        self.datastore = datastore
        self.queries = []

    def execute_query(self, query):
        self.queries.append(query)
        if "from record_quality_findings" in query:
            rows = list(self.datastore.table("record_quality_findings").inserts)
            return [{"record_quality_findings": dict(row)} for row in rows]
        if "from record_quality_issues" in query:
            rows = list(self.datastore.table("record_quality_issues").inserts)
            return [{"record_quality_issues": dict(row)} for row in rows]
        return []


class SidecarHelperTests(unittest.TestCase):
    def test_line_keeps_actual_values_and_omits_them_from_issues(self):
        fields = {
            "Email": {"value": "john.smith@"},
            "Phone": {"value": "12345"},
            "Company": {"value": ""},
            "Lead_Name": {"value": "John Smith"},
        }
        issues = [
            {
                "fieldApiName": "Email",
                "issueType": "INVALID_EMAIL",
                "severity": "HIGH",
                "messageCode": "INVALID_EMAIL_FORMAT",
                "fieldLabel": "Email",
                "validator": "email",
                "importance": None,
                "metricGroup": "VALIDITY",
            },
            {
                "fieldApiName": "Company",
                "issueType": "MISSING_VALUE",
                "severity": "MEDIUM",
                "messageCode": "BUSINESS_CRITICAL_VALUE_MISSING",
                "fieldLabel": "Company",
                "validator": None,
                "importance": "BUSINESS_CRITICAL",
                "metricGroup": "COMPLETENESS",
            },
        ]
        line = build_sidecar_line("crm_1", fields, issues)
        self.assertEqual(line["crmRecordId"], "crm_1")
        self.assertEqual(line["cells"]["Email"], "john.smith@")
        self.assertEqual(line["cells"]["Phone"], "12345")
        self.assertEqual(line["cells"]["Company"], "")
        self.assertEqual(line["cells"]["Lead_Name"], "John Smith")
        self.assertEqual(
            [issue["fieldApiName"] for issue in line["issues"]],
            ["Email", "Company"],
        )
        self.assertNotIn("value", line["issues"][0])
        self.assertEqual(line["issues"][0]["issueType"], "INVALID_EMAIL")
        self.assertEqual(
            compact_issue_type_keys(issues),
            "INVALID_EMAIL,MISSING_VALUE",
        )

    def test_attach_assigns_zero_based_jsonl_line(self):
        lines = []
        first = attach_sidecar_line(
            {
                "crmRecordId": "a",
                "issues": [{"issueType": "INVALID_EMAIL", "fieldApiName": "Email"}],
            },
            {"Email": {"value": "bad@"}},
            lines,
        )
        second = attach_sidecar_line(
            {
                "crmRecordId": "b",
                "issues": [{"issueType": "MISSING_VALUE", "fieldApiName": "Phone"}],
            },
            {"Phone": {"value": ""}},
            lines,
        )
        self.assertEqual(first["jsonlLine"], 0)
        self.assertEqual(second["jsonlLine"], 1)
        self.assertEqual(first["issueTypeKeys"], "INVALID_EMAIL")
        self.assertEqual(len(lines), 2)

    def test_encode_jsonl_writes_one_object_per_line(self):
        payload = encode_fix_jsonl(
            [
                {"crmRecordId": "a", "cells": {"Email": "x@"}, "issues": []},
                {"crmRecordId": "b", "cells": {"Email": ""}, "issues": []},
            ]
        )
        parsed = [
            json.loads(line) for line in payload.decode("utf-8").splitlines() if line
        ]
        self.assertEqual([row["crmRecordId"] for row in parsed], ["a", "b"])
        self.assertEqual(parsed[0]["cells"]["Email"], "x@")

    def test_empty_sidecar_is_still_uploaded(self):
        app = FakeApp()
        with patch.dict(os.environ, {"STRATUS_BUCKET_NAME": "crm-extracts"}):
            key = write_fix_sidecar(app, "scan_9", "Leads", 1, [])
        self.assertEqual(key, "exports/scan_9/fix/Leads/batch-1.jsonl")
        self.assertEqual(app._bucket.uploads[0][0], key)
        self.assertEqual(app._bucket.uploads[0][1], b"")

    def test_write_sidecar_does_not_re_download_extract(self):
        app = FakeApp()
        lines = [
            build_sidecar_line(
                "crm_1",
                {"Email": {"value": "john.smith@"}},
                [
                    {
                        "fieldApiName": "Email",
                        "issueType": "INVALID_EMAIL",
                        "severity": "HIGH",
                        "messageCode": "INVALID_EMAIL_FORMAT",
                        "fieldLabel": "Email",
                    }
                ],
            )
        ]
        with patch.dict(os.environ, {"STRATUS_BUCKET_NAME": "crm-extracts"}):
            key = write_fix_sidecar(app, "scan_9", "Leads", 2, lines)
        self.assertEqual(key, build_fix_object_key("scan_9", "Leads", 2))
        stored = json.loads(app._bucket.objects[key].decode("utf-8").splitlines()[0])
        self.assertEqual(stored["cells"]["Email"], "john.smith@")


def _issue(field, issue_type, extra=None):
    payload = {
        "fieldApiName": field,
        "metricGroup": "VALIDITY" if issue_type.startswith("INVALID") else "COMPLETENESS",
        "issueType": issue_type,
        "severity": "HIGH",
        "messageCode": f"{issue_type}_FORMAT",
        "validator": "email" if issue_type == "INVALID_EMAIL" else None,
        "importance": None,
        "fieldLabel": field,
    }
    if extra:
        payload.update(extra)
    return payload


def _finding(index, issue_count=1):
    issues = [
        _issue("Email", "INVALID_EMAIL")
        for _ in range(issue_count)
    ]
    if issue_count > 1:
        issues = [_issue("Email", "INVALID_EMAIL")] + [
            _issue(f"Field_{offset}", "MISSING_VALUE")
            for offset in range(issue_count - 1)
        ]
    return {
        "findingKey": f"key_{index:03d}",
        "recordKey": f"record_{index:03d}",
        "crmRecordId": f"crm_{index:03d}",
        "ownerKey": "",
        "highestSeverity": "HIGH",
        "missingCount": max(0, issue_count - 1),
        "invalidCount": 1,
        "staleCount": 0,
        "displayName": f"Lead {index}",
        "jsonlLine": index,
        "issueTypeKeys": compact_issue_type_keys(issues),
        "issues": issues,
    }


def _load_processing(worker_root, unique_name):
    import importlib.util

    if str(worker_root) not in sys.path:
        sys.path.insert(0, str(worker_root))
    spec = importlib.util.spec_from_file_location(
        unique_name, worker_root / "pipeline" / "processing.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PersistIndexTests(unittest.TestCase):
    def setUp(self):
        module = _load_processing(ZOHO_WORKER, "zoho_processing_fix_index")
        self.persist = module._persist_record_findings
        self.sample_limit = module.MAX_STORED_FINDINGS_PER_MODULE
        self.issue_limit = module.MAX_STORED_ISSUES_PER_FINDING
        self.zoho_processing = module
        self.datastore = FakeDatastore()
        self.app = types.SimpleNamespace(
            zcql=lambda: FakeZcql(self.datastore),
            datastore=lambda: self.datastore,
        )
        self.scan = {"ROWID": "11", "scan_id": "scan_1"}
        self.module = {"ROWID": "21", "module_api_name": "Leads"}
        self.batch = {"ROWID": "31"}

    def test_all_findings_persisted_issues_remain_sampled(self):
        findings = [_finding(index, issue_count=6) for index in range(45)]
        issue_sample = findings[: self.sample_limit]
        result = self.persist(
            self.app,
            self.scan,
            self.module,
            self.batch,
            "checksum",
            findings,
            issue_sample,
        )
        finding_rows = self.datastore.table("record_quality_findings").inserts
        issue_rows = self.datastore.table("record_quality_issues").inserts
        self.assertEqual(result["affectedRecordCount"], 45)
        self.assertEqual(len(finding_rows), 45)
        self.assertEqual(finding_rows[0]["jsonl_line"], 0)
        self.assertEqual(finding_rows[0]["display_name"], "Lead 0")
        self.assertEqual(finding_rows[0]["schema_version"], "record-findings-v5")
        self.assertEqual(len(issue_rows), self.sample_limit * self.issue_limit)
        sampled_record_keys = {row["record_key"] for row in issue_rows}
        self.assertEqual(len(sampled_record_keys), self.sample_limit)
        self.assertNotIn("record_044", sampled_record_keys)

    def test_salesforce_processing_persist_is_symmetrical(self):
        module = _load_processing(SF_WORKER, "sf_processing_fix_index")
        self.assertEqual(
            self.zoho_processing.MAX_STORED_FINDINGS_PER_MODULE,
            module.MAX_STORED_FINDINGS_PER_MODULE,
        )
        self.assertEqual(
            self.zoho_processing.MAX_STORED_ISSUES_PER_FINDING,
            module.MAX_STORED_ISSUES_PER_FINDING,
        )
        self.assertEqual(
            self.zoho_processing.RECORD_FINDING_SCHEMA_VERSION,
            "record-findings-v5",
        )
        self.assertEqual(
            module.RECORD_FINDING_SCHEMA_VERSION,
            self.zoho_processing.RECORD_FINDING_SCHEMA_VERSION,
        )
        datastore = FakeDatastore()
        app = types.SimpleNamespace(
            zcql=lambda: FakeZcql(datastore),
            datastore=lambda: datastore,
        )
        findings = [_finding(index) for index in range(3)]
        module._persist_record_findings(
            app,
            self.scan,
            {"ROWID": "21", "module_api_name": "Account"},
            self.batch,
            "checksum",
            findings,
            findings[:2],
        )
        self.assertEqual(len(datastore.table("record_quality_findings").inserts), 3)
        self.assertEqual(len(datastore.table("record_quality_issues").inserts), 2)

    def test_retry_replaces_findings_for_the_same_processing_batch(self):
        first = [_finding(index) for index in range(3)]
        self.persist(
            self.app,
            self.scan,
            self.module,
            self.batch,
            "checksum",
            first,
            first,
        )
        first_finding_ids = [
            row["ROWID"]
            for row in self.datastore.table("record_quality_findings").inserts
        ]
        first_issue_ids = [
            row["ROWID"]
            for row in self.datastore.table("record_quality_issues").inserts
        ]
        self.assertEqual(len(first_finding_ids), 3)
        self.assertEqual(len(first_issue_ids), 3)

        second = [_finding(index + 10) for index in range(2)]
        self.persist(
            self.app,
            self.scan,
            self.module,
            self.batch,
            "checksum-retry",
            second,
            second,
        )
        finding_rows = self.datastore.table("record_quality_findings").inserts
        issue_rows = self.datastore.table("record_quality_issues").inserts
        self.assertEqual([row["crm_record_id"] for row in finding_rows], ["crm_010", "crm_011"])
        self.assertEqual(len(issue_rows), 2)
        self.assertTrue(
            set(first_finding_ids).isdisjoint(row["ROWID"] for row in finding_rows)
        )
        self.assertTrue(
            set(first_issue_ids).isdisjoint(row["ROWID"] for row in issue_rows)
        )
        self.assertEqual(
            {str(row_id) for row_id in self.datastore.table("record_quality_findings").deleted},
            {str(row_id) for row_id in first_finding_ids},
        )

    def test_retry_with_no_defects_clears_previous_batch_rows(self):
        first = [_finding(index) for index in range(2)]
        self.persist(
            self.app, self.scan, self.module, self.batch, "checksum", first, first
        )
        self.persist(
            self.app, self.scan, self.module, self.batch, "checksum", [], []
        )
        self.assertEqual(self.datastore.table("record_quality_findings").inserts, [])
        self.assertEqual(self.datastore.table("record_quality_issues").inserts, [])


if __name__ == "__main__":
    unittest.main()
