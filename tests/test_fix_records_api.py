import json
import re
import sys
import types
import unittest
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

from analytics.fix_records import get_fix_records
from storage.extract_store import ExtractStorageError, build_fix_object_key


SCAN_ID = "scan_fix_records_1"
SCAN_ROW = {
    "ROWID": "1001",
    "scan_id": SCAN_ID,
    "crm_provider": "zoho",
    "connection_row_id": "5550000000001",
}


def _jsonl(lines):
    chunks = []
    for line in lines or []:
        chunks.append(json.dumps(line, ensure_ascii=True, separators=(",", ":")))
        chunks.append("\n")
    return "".join(chunks).encode("utf-8")


def _request(**params):
    scalars = {}
    lists = {}
    for key, value in params.items():
        if isinstance(value, list):
            lists[key] = [str(item) for item in value]
            scalars[key] = ",".join(str(item) for item in value)
        elif value is not None:
            scalars[key] = str(value)

    def get(key, default=None):
        return scalars.get(key, default)

    def getlist(key):
        if key in lists:
            return list(lists[key])
        if key in scalars:
            return [scalars[key]]
        return []

    return types.SimpleNamespace(
        args=types.SimpleNamespace(get=get, getlist=getlist)
    )


def _payload(response):
    if hasattr(response, "get_json"):
        return response.get_json()
    if isinstance(response.payload, str):
        return json.loads(response.payload)
    return response.payload


def _finding(
    row_id,
    crm_record_id,
    display_name,
    batch_id,
    jsonl_line,
    owner_key="",
    severity="HIGH",
    issue_type_keys="INVALID_EMAIL",
):
    return {
        "ROWID": str(row_id),
        "crm_record_id": crm_record_id,
        "display_name": display_name,
        "owner_key": owner_key,
        "highest_severity": severity,
        "processing_batch_row_id": str(batch_id),
        "jsonl_line": jsonl_line,
        "issue_type_keys": issue_type_keys,
        "module_api_name": "Leads",
        "schema_version": "record-findings-v5",
        "issue_count": 1,
        "status": "DETECTED",
        "scan_row_id": SCAN_ROW["ROWID"],
    }


def _line(crm_record_id, cells, issues):
    return {"crmRecordId": crm_record_id, "cells": cells, "issues": issues}


def _invalid_email_issue():
    return {
        "fieldApiName": "Email",
        "issueType": "INVALID_EMAIL",
        "severity": "HIGH",
        "messageCode": "INVALID_EMAIL_FORMAT",
        "fieldLabel": "Email",
    }


def _analytics_row():
    return {
        "status": "COMPUTED",
        "metric_group": "record_findings",
        "schema_version": "record-findings-v5",
        "module_api_name": "Leads",
        "aggregate_json": json.dumps(
            {
                "measured": True,
                "affectedRecordCount": 198,
                "issueCount": 612,
            }
        ),
    }


def _module_row():
    return {
        "ROWID": "2001",
        "scan_row_id": SCAN_ROW["ROWID"],
        "module_api_name": "Leads",
        "field_allowlist_json": json.dumps(["id", "Email", "Company", "Last_Name"]),
        "field_metadata_json": json.dumps(
            [
                {"apiName": "id", "label": "Record Id"},
                {"apiName": "Email", "label": "Email"},
                {"apiName": "Company", "label": "Company"},
                {"apiName": "Last_Name", "label": "Last Name"},
            ]
        ),
    }


def _in_list(query, column):
    match = re.search(rf"{re.escape(column)} in \(([^)]+)\)", query)
    if not match:
        return None
    values = []
    for part in match.group(1).split(","):
        item = part.strip()
        if item.startswith("'") and item.endswith("'"):
            values.append(item[1:-1].replace("''", "'"))
        else:
            values.append(item)
    return values


def _quoted(query, column):
    match = re.search(rf"{re.escape(column)} = '((?:[^']|'')*)'", query)
    if not match:
        return None
    return match.group(1).replace("''", "'")


def _unquoted(query, column):
    match = re.search(rf"{re.escape(column)} = (\d+)", query)
    if not match:
        return None
    return match.group(1)


def _rowid_greater_than(query):
    match = re.search(r"ROWID > (\d+)", query)
    if not match:
        return None
    return int(match.group(1))


def _like_clauses(query, column):
    return [
        match.replace("''", "'")
        for match in re.findall(
            rf"{re.escape(column)} like '((?:[^']|'')*)'", query
        )
    ]


def _limit(query):
    match = re.search(r"limit (\d+),(\d+)", query)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _like_match(value, pattern):
    text = str(value or "")
    if pattern.endswith("%") and not pattern.startswith("%"):
        return text.startswith(pattern[:-1])
    if pattern.startswith("%") and pattern.endswith("%"):
        return pattern[1:-1] in text
    if pattern.startswith("%"):
        return text.endswith(pattern[1:])
    return text == pattern


class FilterZcql:
    def __init__(self, tables):
        self.tables = tables
        self.queries = []

    def execute_query(self, query):
        self.queries.append(query)
        if "from record_quality_issues" in query:
            raise AssertionError("Fix records must not query record_quality_issues")
        if "count(*)" in query.replace(" ", "").lower():
            raise AssertionError("Fix records must not COUNT(*) findings")
        table_name = None
        for name in self.tables:
            if f"from {name}" in query:
                table_name = name
                break
        if table_name is None:
            return []
        rows = [dict(row) for row in self.tables[table_name]]
        if table_name == "record_quality_findings":
            rows = [row for row in rows if self._finding_matches(row, query)]
            rows.sort(key=lambda row: int(row["ROWID"]))
            paging = _limit(query)
            if paging:
                offset, size = paging
                rows = rows[offset : offset + size]
        elif table_name == "processing_batches":
            ids = _in_list(query, "ROWID")
            if ids:
                rows = [row for row in rows if str(row["ROWID"]) in set(ids)]
        return [{table_name: row} for row in rows]

    def _finding_matches(self, row, query):
        scan_row_id = _unquoted(query, "scan_row_id")
        if scan_row_id and str(row.get("scan_row_id")) != scan_row_id:
            return False
        module_name = _quoted(query, "module_api_name")
        if module_name and str(row.get("module_api_name")) != module_name:
            return False
        schema = _quoted(query, "schema_version")
        if schema and str(row.get("schema_version")) != schema:
            return False
        if "status = 'DETECTED'" in query and str(row.get("status")) != "DETECTED":
            return False
        if "issue_count > 0" in query and int(row.get("issue_count") or 0) <= 0:
            return False
        min_row = _rowid_greater_than(query)
        if min_row is not None and int(row["ROWID"]) <= min_row:
            return False
        owners = _in_list(query, "owner_key")
        allow_unassigned = "owner_key = ''" in query
        if owners is not None or allow_unassigned:
            owner = str(row.get("owner_key") or "")
            matched = False
            if owners is not None and owner in set(owners):
                matched = True
            if allow_unassigned and owner == "":
                matched = True
            if not matched:
                return False
        severities = _in_list(query, "highest_severity")
        if severities is not None and str(row.get("highest_severity")) not in set(
            severities
        ):
            return False
        if "issue_type_keys" in query:
            keys = str(row.get("issue_type_keys") or "")
            tokens = [part for part in keys.split(",") if part]
            wanted = set()
            exact = re.findall(r"issue_type_keys = '((?:[^']|'')*)'", query)
            wanted.update(item.replace("''", "'") for item in exact)
            for pattern in _like_clauses(query, "issue_type_keys"):
                candidate = pattern.replace("%", "").replace(",", "")
                if candidate:
                    wanted.add(candidate)
            if wanted and not (wanted & set(tokens)):
                return False
        crm_id = _quoted(query, "crm_record_id")
        display_exact = _quoted(query, "display_name")
        display_likes = _like_clauses(query, "display_name")
        if crm_id is not None or display_exact is not None or display_likes:
            matched = False
            if crm_id is not None and str(row.get("crm_record_id")) == crm_id:
                matched = True
            if display_exact is not None and str(row.get("display_name")) == display_exact:
                matched = True
            for pattern in display_likes:
                if _like_match(row.get("display_name"), pattern):
                    matched = True
            if not matched:
                return False
        return True


class FakeApp:
    def __init__(self, zcql):
        self._zcql = zcql

    def zcql(self):
        return self._zcql


class FixRecordsApiTests(unittest.TestCase):
    def setUp(self):
        self.findings = [
            _finding(10, "crm_001", "Acme Lead", 21, 0, owner_key="owner_a"),
            _finding(
                11,
                "crm_002",
                "Northwind",
                21,
                1,
                owner_key="owner_b",
                severity="MEDIUM",
                issue_type_keys="MISSING_VALUE",
            ),
            _finding(12, "crm_003", "Beta Corp", 22, 0, owner_key="owner_a"),
        ]
        self.sidecars = {
            build_fix_object_key(SCAN_ID, "Leads", 1): _jsonl(
                [
                    _line(
                        "crm_001",
                        {
                            "id": "crm_001",
                            "Email": "john.smith@",
                            "Company": "Acme",
                            "Last_Name": "Smith",
                        },
                        [_invalid_email_issue()],
                    ),
                    _line(
                        "crm_002",
                        {
                            "id": "crm_002",
                            "Email": "",
                            "Company": "Northwind",
                            "Last_Name": "Lee",
                        },
                        [
                            {
                                "fieldApiName": "Email",
                                "issueType": "MISSING_VALUE",
                                "severity": "MEDIUM",
                                "messageCode": "BUSINESS_CRITICAL_VALUE_MISSING",
                                "fieldLabel": "Email",
                            }
                        ],
                    ),
                ]
            ),
            build_fix_object_key(SCAN_ID, "Leads", 2): _jsonl(
                [
                    _line(
                        "crm_003",
                        {
                            "id": "crm_003",
                            "Email": "not-an-email",
                            "Company": "",
                            "Last_Name": "Beta",
                        },
                        [_invalid_email_issue()],
                    )
                ]
            ),
        }
        self.extract_calls = []
        self.owned_calls = []
        self.zcql = FilterZcql(
            {
                "analytics_results": [_analytics_row()],
                "scan_module_runs": [_module_row()],
                "record_quality_findings": self.findings,
                "processing_batches": [
                    {"ROWID": "21", "batch_number": 1},
                    {"ROWID": "22", "batch_number": 2},
                ],
            }
        )

    def _get_extract(self, key, app=None):
        del app
        self.extract_calls.append(key)
        if "/fix/" not in key:
            raise AssertionError("Fix records must not download the Bulk extract")
        payload = self.sidecars.get(key)
        if payload is None:
            raise ExtractStorageError("EXTRACT_NOT_FOUND", "missing sidecar")
        return payload

    def _owned(self, zcql, scan_id, user_id):
        del zcql, user_id
        self.owned_calls.append(scan_id)
        if scan_id != SCAN_ID:
            return None
        return dict(SCAN_ROW)

    def _call(self, **params):
        with patch(
            "analytics.fix_records.zcatalyst_sdk.initialize",
            return_value=FakeApp(self.zcql),
        ), patch(
            "analytics.fix_records.get_current_user_id", return_value="user-1"
        ), patch(
            "analytics.fix_records.find_owned_scan", side_effect=self._owned
        ), patch(
            "analytics.fix_records.get_extract", side_effect=self._get_extract
        ):
            return get_fix_records(_request(**params), object(), SCAN_ID)

    def test_module_is_required(self):
        response = self._call()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(_payload(response)["error"]["code"], "MODULE_REQUIRED")
        self.assertFalse(self.extract_calls)
        self.assertTrue(self.owned_calls)

    def test_cursor_pagination(self):
        extra = [
            _finding(13 + index, f"crm_{index + 4:03d}", f"Lead {index}", 21, 0)
            for index in range(18)
        ]
        self.findings.extend(extra)
        self.zcql.tables["record_quality_findings"] = self.findings
        first = self._call(module="Leads", pageSize="20")
        first_payload = _payload(first)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(len(first_payload["rows"]), 20)
        self.assertTrue(first_payload["hasMore"])
        self.assertEqual(first_payload["nextCursor"], self.findings[19]["ROWID"])
        self.assertEqual(first_payload["pageSize"], 20)

        second = self._call(module="Leads", pageSize="20", cursor=first_payload["nextCursor"])
        second_payload = _payload(second)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(len(second_payload["rows"]), 1)
        self.assertFalse(second_payload["hasMore"])
        self.assertIsNone(second_payload["nextCursor"])
        self.assertEqual(second_payload["rows"][0]["cells"]["Email"], "john.smith@")
        self.assertTrue(
            any("ROWID > " in query for query in self.zcql.queries)
        )

    def _add_searchable_record(self):
        self.findings.append(
            _finding(
                200,
                "1086951000000440603",
                "Michael Ruta (Sample)",
                24,
                0,
                owner_key="owner_mike",
            )
        )
        self.zcql.tables["record_quality_findings"] = self.findings
        self.zcql.tables["processing_batches"].append(
            {"ROWID": "24", "batch_number": 3}
        )
        self.sidecars[build_fix_object_key(SCAN_ID, "Leads", 3)] = _jsonl(
            [
                _line(
                    "1086951000000440603",
                    {
                        "id": "1086951000000440603",
                        "Email": "noemail.invalid",
                        "First_Name": "Michael",
                        "Last_Name": "Ruta",
                        "Company": "Contoso",
                        "Phone": "8500001234",
                        "Owner": "Ada Lovelace",
                        "Created_By": "System User",
                    },
                    [_invalid_email_issue()],
                )
            ]
        )

    def _ids(self, payload):
        return [row["crmRecordId"] for row in payload["rows"]]

    def test_q_matches_display_name_prefix_and_crm_id(self):
        by_name = _payload(self._call(module="Leads", q="North"))
        self.assertEqual(self._ids(by_name), ["crm_002"])
        by_id = _payload(self._call(module="Leads", q="crm_003"))
        self.assertEqual(self._ids(by_id), ["crm_003"])

    def test_q_matches_display_name_partial(self):
        suffix = _payload(self._call(module="Leads", q="wind"))
        self.assertEqual(self._ids(suffix), ["crm_002"])
        self._add_searchable_record()
        payload = _payload(self._call(module="Leads", q="Ruta"))
        self.assertEqual(self._ids(payload), ["1086951000000440603"])
        first_name = _payload(self._call(module="Leads", q="Michael"))
        self.assertEqual(self._ids(first_name), ["1086951000000440603"])

    def test_q_matches_record_id_partial(self):
        self._add_searchable_record()
        by_full = _payload(self._call(module="Leads", q="1086951000000440603"))
        self.assertEqual(self._ids(by_full), ["1086951000000440603"])
        by_partial = _payload(self._call(module="Leads", q="440603"))
        self.assertEqual(self._ids(by_partial), ["1086951000000440603"])

    def test_q_matches_email(self):
        payload = _payload(self._call(module="Leads", q="john.smith@"))
        self.assertEqual(self._ids(payload), ["crm_001"])
        self._add_searchable_record()
        invalid = _payload(self._call(module="Leads", q="noemail.invalid"))
        self.assertEqual(self._ids(invalid), ["1086951000000440603"])

    def test_q_matches_another_visible_field(self):
        company = _payload(self._call(module="Leads", q="Acme"))
        self.assertEqual(self._ids(company), ["crm_001"])
        last_name = _payload(self._call(module="Leads", q="Lee"))
        self.assertEqual(self._ids(last_name), ["crm_002"])
        self._add_searchable_record()
        phone = _payload(self._call(module="Leads", q="850000"))
        self.assertEqual(self._ids(phone), ["1086951000000440603"])
        owner = _payload(self._call(module="Leads", q="Ada Lovelace"))
        self.assertEqual(self._ids(owner), ["1086951000000440603"])

    def test_q_is_case_insensitive(self):
        payload = _payload(self._call(module="Leads", q="nOrThWiNd"))
        self.assertEqual(self._ids(payload), ["crm_002"])
        self._add_searchable_record()
        mixed = _payload(self._call(module="Leads", q="MICHAEL ruta"))
        self.assertEqual(self._ids(mixed), ["1086951000000440603"])
        last = _payload(self._call(module="Leads", q="rUtA"))
        self.assertEqual(self._ids(last), ["1086951000000440603"])

    def test_q_no_match_returns_empty_page(self):
        payload = _payload(self._call(module="Leads", q="zz-no-such-record"))
        self.assertEqual(payload["rows"], [])
        self.assertFalse(payload["hasMore"])
        self.assertIsNone(payload["nextCursor"])
        self.assertEqual(payload["kpis"]["affectedRecordCount"], 198)

    def test_q_search_stays_tenant_and_scan_scoped(self):
        def deny(zcql, scan_id, user_id):
            del zcql, scan_id, user_id
            self.owned_calls.append("denied")
            return None

        with patch(
            "analytics.fix_records.zcatalyst_sdk.initialize",
            return_value=FakeApp(self.zcql),
        ), patch(
            "analytics.fix_records.get_current_user_id", return_value="stranger"
        ), patch(
            "analytics.fix_records.find_owned_scan", side_effect=deny
        ), patch(
            "analytics.fix_records.get_extract", side_effect=self._get_extract
        ):
            response = get_fix_records(
                _request(module="Leads", q="Michael"), object(), SCAN_ID
            )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(_payload(response)["error"]["code"], "SCAN_NOT_FOUND")
        self.assertFalse(self.extract_calls)
        self.assertFalse(
            any("from record_quality_findings" in query for query in self.zcql.queries)
        )

    def test_q_continues_past_the_first_index_page(self):
        extra = [
            _finding(13 + index, f"crm_{index + 4:03d}", f"Lead {index}", 21, 0)
            for index in range(50)
        ]
        self.findings.extend(extra)
        self.zcql.tables["record_quality_findings"] = self.findings
        self._add_searchable_record()
        payload = _payload(self._call(module="Leads", q="noemail.invalid"))
        self.assertEqual(self._ids(payload), ["1086951000000440603"])
        self.assertGreaterEqual(
            len(
                [
                    query
                    for query in self.zcql.queries
                    if "from record_quality_findings" in query
                ]
            ),
            2,
        )
        self.assertEqual(
            self.extract_calls.count(build_fix_object_key(SCAN_ID, "Leads", 1)),
            1,
        )

    def test_owner_severity_and_issue_type_filters(self):
        owner_payload = _payload(self._call(module="Leads", owners="owner_b"))
        self.assertEqual([row["crmRecordId"] for row in owner_payload["rows"]], ["crm_002"])
        severity_payload = _payload(self._call(module="Leads", severity="MEDIUM"))
        self.assertEqual(
            [row["crmRecordId"] for row in severity_payload["rows"]], ["crm_002"]
        )
        issue_payload = _payload(self._call(module="Leads", issueType="MISSING_VALUE"))
        self.assertEqual([row["crmRecordId"] for row in issue_payload["rows"]], ["crm_002"])
        combo = _payload(
            self._call(
                module="Leads",
                owners="owner_a",
                severity="HIGH",
                issueType="INVALID_EMAIL",
            )
        )
        self.assertEqual(
            [row["crmRecordId"] for row in combo["rows"]],
            ["crm_001", "crm_003"],
        )

    def test_jsonl_hydration_across_batches(self):
        payload = _payload(self._call(module="Leads"))
        self.assertEqual(payload["kpis"]["affectedRecordCount"], 198)
        self.assertEqual(payload["kpis"]["issueCount"], 612)
        self.assertEqual(len(payload["rows"]), 3)
        self.assertEqual(
            payload["columns"][1],
            {"apiName": "Email", "label": "Email"},
        )
        self.assertEqual(
            sorted(self.extract_calls),
            [
                build_fix_object_key(SCAN_ID, "Leads", 1),
                build_fix_object_key(SCAN_ID, "Leads", 2),
            ],
        )
        self.assertEqual(self.extract_calls.count(self.extract_calls[0]), 1)
        first = payload["rows"][0]
        self.assertEqual(first["cells"]["Email"], "john.smith@")
        third = payload["rows"][2]
        self.assertEqual(third["cells"]["Email"], "not-an-email")
        self.assertEqual(third["cells"]["Company"], "")
        self.assertEqual(self.owned_calls[0], SCAN_ID)
        self.assertFalse(
            any("from record_quality_issues" in query for query in self.zcql.queries)
        )

    def test_missing_sidecar_returns_fix_index_unavailable(self):
        self.sidecars.clear()
        response = self._call(module="Leads")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(_payload(response)["error"]["code"], "FIX_INDEX_UNAVAILABLE")

    def test_v4_analytics_returns_fix_index_unavailable(self):
        self.zcql.tables["analytics_results"] = [
            {
                "status": "COMPUTED",
                "metric_group": "record_findings",
                "schema_version": "record-findings-v4",
                "module_api_name": "Leads",
                "aggregate_json": json.dumps(
                    {"measured": True, "affectedRecordCount": 10, "issueCount": 10}
                ),
            }
        ]
        response = self._call(module="Leads")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(_payload(response)["error"]["code"], "FIX_INDEX_UNAVAILABLE")
        self.assertFalse(self.extract_calls)

    def test_cross_tenant_scan_is_not_found(self):
        def deny(zcql, scan_id, user_id):
            del zcql, scan_id, user_id
            self.owned_calls.append("denied")
            return None

        with patch(
            "analytics.fix_records.zcatalyst_sdk.initialize",
            return_value=FakeApp(self.zcql),
        ), patch(
            "analytics.fix_records.get_current_user_id", return_value="stranger"
        ), patch(
            "analytics.fix_records.find_owned_scan", side_effect=deny
        ), patch(
            "analytics.fix_records.get_extract", side_effect=self._get_extract
        ):
            response = get_fix_records(_request(module="Leads"), object(), SCAN_ID)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(_payload(response)["error"]["code"], "SCAN_NOT_FOUND")
        self.assertFalse(self.extract_calls)
        self.assertFalse(
            any("from record_quality_findings" in query for query in self.zcql.queries)
        )

    def test_actual_defective_values_are_preserved(self):
        payload = _payload(self._call(module="Leads"))
        emails = [row["cells"]["Email"] for row in payload["rows"]]
        self.assertEqual(emails, ["john.smith@", "", "not-an-email"])
        self.assertNotIn("Invalid", json.dumps(payload["rows"]))
        self.assertEqual(payload["rows"][1]["cells"]["Email"], "")
        self.assertEqual(payload["rows"][1]["issues"][0]["issueType"], "MISSING_VALUE")

    def test_kpis_come_from_analytics_not_page_size(self):
        payload = _payload(self._call(module="Leads", pageSize="20"))
        self.assertEqual(payload["kpis"]["affectedRecordCount"], 198)
        self.assertNotEqual(payload["kpis"]["affectedRecordCount"], len(payload["rows"]))


if __name__ == "__main__":
    unittest.main()
