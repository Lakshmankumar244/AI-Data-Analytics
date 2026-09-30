import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS_ROOT = ROOT / "functions"
ZOHO_WORKER = FUNCTIONS_ROOT / "ai_data_analytics_worker"
SF_WORKER = FUNCTIONS_ROOT / "ai_data_analytics_salesforce_worker"

if "zcatalyst_sdk" not in sys.modules:
    stub = types.ModuleType("zcatalyst_sdk")
    stub.initialize = lambda: None
    sys.modules["zcatalyst_sdk"] = stub

sys.path.insert(0, str(ROOT / "tests"))
from test_fix_sidecar import (  # noqa: E402
    FakeApp,
    FakeDatastore,
    FakeZcql,
    _load_processing,
)


def _plan(processing, field_names, metadata, module_name="Vendors", depth="deep"):
    fields = ["id", *field_names]
    field_metadata = {
        "id": {"apiName": "id", "label": "Id", "systemMandatory": True},
        **metadata,
    }
    for name in fields:
        field_metadata.setdefault(name, {"apiName": name, "label": name})
    return processing._build_field_plan(fields, field_metadata, module_name, depth)


def _evaluate(processing, values, field_names, metadata, module_name="Vendors", depth="deep"):
    plan = _plan(processing, field_names, metadata, module_name, depth)
    row = {"id": values.get("id", "crm_1"), **values}
    mapping = {name: name for name in ["id", *field_names]}
    return processing._evaluate_record(row, plan, mapping)


def _issue_types(issues):
    return [issue["issueType"] for issue in issues]


class QualityValidationTests(unittest.TestCase):
    def setUp(self):
        self.zoho = _load_processing(ZOHO_WORKER, "zoho_quality_validation")
        self.salesforce = _load_processing(SF_WORKER, "sf_quality_validation")

    def test_mandatory_missing_field_stays_high(self):
        for processing in (self.zoho, self.salesforce):
            _fields, issues = _evaluate(
                processing,
                {"Last_Name": ""},
                ["Last_Name"],
                {
                    "Last_Name": {
                        "apiName": "Last_Name",
                        "label": "Last Name",
                        "systemMandatory": True,
                    }
                },
                module_name="Leads",
                depth="quick",
            )
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0]["issueType"], "MISSING_VALUE")
            self.assertEqual(issues[0]["severity"], "HIGH")
            self.assertEqual(issues[0]["messageCode"], "SYSTEM_MANDATORY_VALUE_MISSING")
            self.assertNotIn("INVALID_PHONE", _issue_types(issues))

    def test_optional_empty_field_is_low_missing_value(self):
        for processing in (self.zoho, self.salesforce):
            _fields, issues = _evaluate(
                processing,
                {"Custom_Field_X": None},
                ["Custom_Field_X"],
                {
                    "Custom_Field_X": {
                        "apiName": "Custom_Field_X",
                        "label": "Custom Field X",
                    }
                },
                module_name="Vendors",
                depth="deep",
            )
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0]["issueType"], "MISSING_VALUE")
            self.assertEqual(issues[0]["severity"], "LOW")
            self.assertEqual(issues[0]["messageCode"], "OPTIONAL_VALUE_MISSING")
            self.assertEqual(issues[0]["importance"], "OPTIONAL")

    def test_optional_empty_phone_is_low_missing_not_invalid(self):
        for processing in (self.zoho, self.salesforce):
            fields, issues = _evaluate(
                processing,
                {"Phone": "  "},
                ["Phone"],
                {"Phone": {"apiName": "Phone", "label": "Phone"}},
                module_name="Vendors",
                depth="deep",
            )
            self.assertEqual(fields["Phone"]["value"], "")
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0]["issueType"], "MISSING_VALUE")
            self.assertEqual(issues[0]["severity"], "LOW")
            self.assertEqual(issues[0]["messageCode"], "OPTIONAL_VALUE_MISSING")
            self.assertNotIn("INVALID_PHONE", _issue_types(issues))

    def test_all_zero_phone_is_high_invalid_phone(self):
        for processing in (self.zoho, self.salesforce):
            _fields, issues = _evaluate(
                processing,
                {"Phone": "0000000000"},
                ["Phone"],
                {"Phone": {"apiName": "Phone", "label": "Phone"}},
                module_name="Vendors",
                depth="deep",
            )
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0]["issueType"], "INVALID_PHONE")
            self.assertEqual(issues[0]["severity"], "HIGH")
            self.assertEqual(issues[0]["messageCode"], "INVALID_PHONE_FORMAT")
            self.assertTrue(processing._is_valid("0000000000", "phone") is False)
            self.assertTrue(processing._is_valid("000-000-0000", "phone") is False)

    def test_short_invalid_phone_stays_high_invalid_phone(self):
        for processing in (self.zoho, self.salesforce):
            _fields, issues = _evaluate(
                processing,
                {"Phone": "12345"},
                ["Phone"],
                {"Phone": {"apiName": "Phone", "label": "Phone"}},
                module_name="Vendors",
                depth="deep",
            )
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0]["issueType"], "INVALID_PHONE")
            self.assertEqual(issues[0]["severity"], "HIGH")

    def test_existing_valid_phone_formats_are_not_invalid(self):
        valid_values = (
            "9876543210",
            "+1 415-555-2671",
            "(415) 555-2671",
            "1234567",
            "123456789012345",
        )
        for processing in (self.zoho, self.salesforce):
            for value in valid_values:
                with self.subTest(worker=processing.__name__, value=value):
                    self.assertTrue(processing._is_valid(value, "phone"))
                    _fields, issues = _evaluate(
                        processing,
                        {"Phone": value},
                        ["Phone"],
                        {"Phone": {"apiName": "Phone", "label": "Phone"}},
                        module_name="Vendors",
                        depth="deep",
                    )
                    self.assertNotIn("INVALID_PHONE", _issue_types(issues))
                    self.assertNotIn("MISSING_VALUE", _issue_types(issues))

    def test_business_critical_empty_phone_on_leads_is_unchanged(self):
        _fields, issues = _evaluate(
            self.zoho,
            {"Phone": ""},
            ["Phone"],
            {"Phone": {"apiName": "Phone", "label": "Phone"}},
            module_name="Leads",
            depth="presales",
        )
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["issueType"], "MISSING_VALUE")
        self.assertEqual(issues[0]["severity"], "MEDIUM")
        self.assertEqual(issues[0]["messageCode"], "BUSINESS_CRITICAL_VALUE_MISSING")
        self.assertNotIn("INVALID_PHONE", _issue_types(issues))

    def test_optional_missing_finding_reaches_fix_sidecar_and_index(self):
        processing = self.zoho
        fields, issues = _evaluate(
            processing,
            {"id": "crm_opt_1", "Website": ""},
            ["Website"],
            {"Website": {"apiName": "Website", "label": "Website"}},
            module_name="Vendors",
            depth="deep",
        )
        scan = {"ROWID": "11", "scan_id": "scan_opt"}
        module = {"ROWID": "21", "module_api_name": "Vendors"}
        finding = processing._record_finding_candidate(
            fields, issues, None, scan, module, "checksum"
        )
        self.assertIsNotNone(finding)
        self.assertEqual(finding["highestSeverity"], "LOW")
        self.assertEqual(finding["missingCount"], 1)
        self.assertEqual(finding["invalidCount"], 0)

        jsonl_lines = []
        attached = processing._attach_sidecar_line(finding, fields, jsonl_lines)
        self.assertEqual(attached["jsonlLine"], 0)
        self.assertEqual(attached["issueTypeKeys"], "MISSING_VALUE")
        self.assertEqual(jsonl_lines[0]["cells"]["Website"], "")
        self.assertEqual(jsonl_lines[0]["issues"][0]["issueType"], "MISSING_VALUE")
        self.assertEqual(jsonl_lines[0]["issues"][0]["severity"], "LOW")

        datastore = FakeDatastore()
        app = types.SimpleNamespace(
            zcql=lambda: FakeZcql(datastore),
            datastore=lambda: datastore,
        )
        processing._persist_record_findings(
            app,
            scan,
            module,
            {"ROWID": "31"},
            "checksum",
            [attached],
            [attached],
        )
        rows = datastore.table("record_quality_findings").inserts
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["schema_version"], "record-findings-v5")
        self.assertEqual(rows[0]["highest_severity"], "LOW")
        self.assertEqual(rows[0]["issue_type_keys"], "MISSING_VALUE")
        self.assertEqual(rows[0]["jsonl_line"], 0)
        self.assertEqual(rows[0]["crm_record_id"], "crm_opt_1")

        with patch.dict(os.environ, {"STRATUS_BUCKET_NAME": "crm-extracts"}):
            key = processing._write_fix_sidecar(
                FakeApp(), scan["scan_id"], module["module_api_name"], 1, jsonl_lines
            )
        self.assertEqual(key, "exports/scan_opt/fix/Vendors/batch-1.jsonl")


if __name__ == "__main__":
    unittest.main()
