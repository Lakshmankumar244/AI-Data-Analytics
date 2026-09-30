import json
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
    flask.make_response = lambda *args, **kwargs: None
    flask.redirect = lambda *args, **kwargs: None
    sys.modules["flask"] = flask

if "zcatalyst_sdk" not in sys.modules:
    zcatalyst_sdk = types.ModuleType("zcatalyst_sdk")
    zcatalyst_sdk.initialize = lambda: None
    sys.modules["zcatalyst_sdk"] = zcatalyst_sdk

from salesforce.scan_create import (
    SALESFORCE_CRM_PROVIDER,
    SALESFORCE_SCAN_CLOCK_FIELDS,
    accessible_salesforce_object_names,
    build_salesforce_module_field_plan,
    create_salesforce_scan,
    require_salesforce_timezone,
)


def describe_field(name, field_type="string", **overrides):
    field = {
        "name": name,
        "label": name,
        "type": field_type,
        "nillable": True,
        "unique": False,
        "externalId": False,
        "createable": True,
        "updateable": True,
        "calculated": False,
        "custom": name.endswith("__c"),
        "filterable": True,
        "restrictedPicklist": False,
        "referenceTo": [],
        "relationshipName": None,
        "length": 255,
        "deprecatedAndHidden": False,
        "nameField": False,
        "extraTypeInfo": None,
    }
    field.update(overrides)
    return field


def id_field():
    return describe_field(
        "Id",
        "id",
        nillable=False,
        unique=True,
        createable=False,
        updateable=False,
        custom=False,
        length=18,
    )


def created_date_field():
    return describe_field(
        "CreatedDate",
        "datetime",
        nillable=False,
        createable=False,
        updateable=False,
        custom=False,
        length=0,
    )


def last_modified_date_field():
    return describe_field(
        "LastModifiedDate",
        "datetime",
        nillable=False,
        createable=False,
        updateable=False,
        custom=False,
        length=0,
    )


def object_describe(api_name, extra_fields):
    return {
        "name": api_name,
        "label": api_name,
        "custom": False,
        "queryable": True,
        "fields": [id_field(), created_date_field(), last_modified_date_field(), *extra_fields],
    }


ACCOUNT_DESCRIBE = object_describe(
    "Account",
    [describe_field("Name", nillable=False, nameField=True, custom=False)],
)
CONTACT_DESCRIBE = object_describe(
    "Contact",
    [
        describe_field("LastName", nillable=False, nameField=True, custom=False),
        describe_field("FirstName", custom=False),
        describe_field("Email", "email", custom=False),
    ],
)
OPPORTUNITY_DESCRIBE = object_describe(
    "Opportunity",
    [
        describe_field("Name", nillable=False, nameField=True, custom=False),
        describe_field("StageName", "picklist", nillable=False, custom=False),
        describe_field("CloseDate", "date", nillable=False, custom=False),
    ],
)


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

    def insert_rows(self, rows):
        stored = []
        for row in rows:
            stored.append(self.insert_row(row))
        return stored

    def update_row(self, row):
        self.updates.append(dict(row))
        return row


class FakeDatastore:
    def __init__(self):
        self.tables = {"scan_jobs": FakeTable(), "scan_module_runs": FakeTable()}
        self.table_names = []

    def table(self, name):
        self.table_names.append(name)
        if name not in self.tables:
            self.tables[name] = FakeTable()
        return self.tables[name]


class FakeZcql:
    def __init__(self, results=None):
        self.results = results or []
        self.queries = []

    def execute_query(self, query):
        self.queries.append(query)
        return list(self.results)


CONNECTION = {
    "ROWID": "555",
    "user_id": "user-1",
    "status": "connected",
    "is_active": True,
    "salesforce_org_id": "00D5g00000OrgIdAAA",
    "organization_name": "Acme",
}

PAYLOAD = {
    "modules": ["Account"],
    "depth": "quick",
    "clock": "created",
    "range": {"id": "7d"},
}


class SalesforceClockAndTimezoneTests(unittest.TestCase):
    def test_created_and_modified_map_to_salesforce_fields(self):
        self.assertEqual(SALESFORCE_SCAN_CLOCK_FIELDS["created"], "CreatedDate")
        self.assertEqual(SALESFORCE_SCAN_CLOCK_FIELDS["modified"], "LastModifiedDate")

    def test_zoho_clock_mapping_is_unchanged(self):
        source = (Path(FUNCTION_ROOT) / "common" / "core.py").read_text(encoding="utf-8")
        self.assertIn(
            'SCAN_CLOCK_FIELDS = {"created": "Created_Time", "modified": "Modified_Time"}',
            source,
        )

    def test_timezone_is_taken_from_salesforce_sid_key(self):
        self.assertEqual(
            require_salesforce_timezone({"timeZone": "America/Los_Angeles"}),
            "America/Los_Angeles",
        )

    def test_missing_timezone_fails_closed(self):
        with self.assertRaises(ValueError):
            require_salesforce_timezone({"timeZone": ""})
        with self.assertRaises(ValueError):
            require_salesforce_timezone({"timeZone": "Not/AZone"})


class SalesforceObjectAndFieldPlanTests(unittest.TestCase):
    def test_account_and_opportunity_keep_salesforce_api_names(self):
        names = accessible_salesforce_object_names(
            [
                {"apiName": "Account", "label": "Account"},
                {"apiName": "Contact", "label": "Contact"},
                {"apiName": "Opportunity", "label": "Opportunity"},
            ]
        )
        self.assertEqual(names, {"Account", "Contact", "Opportunity"})
        self.assertNotIn("Accounts", names)
        self.assertNotIn("Deals", names)

    def test_field_plan_stores_salesforce_allowlist_and_metadata(self):
        allowlist, metadata = build_salesforce_module_field_plan(
            ACCOUNT_DESCRIBE, "CreatedDate"
        )
        self.assertIn("Id", allowlist)
        self.assertIn("CreatedDate", allowlist)
        self.assertIn("LastModifiedDate", allowlist)
        self.assertNotIn("Created_Time", allowlist)
        by_name = {item["apiName"]: item for item in metadata}
        self.assertEqual(by_name["CreatedDate"]["apiName"], "CreatedDate")
        self.assertEqual(by_name["Id"]["apiName"], "Id")

    def test_clock_field_must_exist_on_the_object(self):
        payload = {
            "name": "Custom__c",
            "fields": [id_field()],
        }
        with self.assertRaises(ValueError):
            build_salesforce_module_field_plan(payload, "CreatedDate")


class SalesforceScanCreateTests(unittest.TestCase):
    def setUp(self):
        self.enqueue_patcher = patch(
            "salesforce.scan_create._enqueue_salesforce_worker",
            return_value={
                "ok": True,
                "submitted": True,
                "alreadyActive": False,
                "task": {
                    "task_id": "task_sf_test",
                    "status": "QUEUED",
                    "task_type": "ORCHESTRATE_SALESFORCE_SCAN",
                    "scan_row_id": "1",
                },
                "jobPoolName": "sfDataAnalyticsWorkerPool",
                "functionName": "ai_data_analytics_salesforce_worker",
            },
        )
        self.enqueue = self.enqueue_patcher.start()
        self.addCleanup(self.enqueue_patcher.stop)
        self.directory_patcher = patch(
            "salesforce.user_directory.sync_salesforce_owner_directory",
            return_value={
                "refreshed": True,
                "apiCalls": 1,
                "counts": {"user": 1, "queue": 0, "group": 0},
                "warning": None,
            },
        )
        self.directory_sync = self.directory_patcher.start()
        self.addCleanup(self.directory_patcher.stop)

    def test_create_scan_persists_salesforce_native_plan(self):
        datastore = FakeDatastore()
        zcql = FakeZcql()
        describes = {
            "Account": ACCOUNT_DESCRIBE,
            "Contact": CONTACT_DESCRIBE,
            "Opportunity": OPPORTUNITY_DESCRIBE,
        }
        with patch(
            "salesforce.client.get_salesforce_access_token",
            return_value=("stored-access-token", "https://example.my.salesforce.com"),
        ), patch(
            "salesforce.client.fetch_salesforce_organization",
            return_value={
                "id": "00D5g00000OrgIdAAA",
                "name": "Acme",
                "timeZone": "America/Los_Angeles",
            },
        ), patch(
            "salesforce.client.persist_salesforce_organization_name"
        ), patch(
            "salesforce.client.fetch_accessible_sobjects",
            return_value=[
                {"apiName": "Account", "label": "Account"},
                {"apiName": "Contact", "label": "Contact"},
                {"apiName": "Opportunity", "label": "Opportunity"},
            ],
        ), patch(
            "salesforce.describe.fetch_sobject_describe",
            side_effect=lambda token, instance, name: describes[name],
        ):
            status, body = create_salesforce_scan(
                datastore,
                zcql,
                CONNECTION,
                {
                    "modules": ["Account", "Contact", "Opportunity"],
                    "depth": "quick",
                    "clock": "created",
                    "range": {"id": "7d"},
                },
            )
        self.assertEqual(status, 201)
        self.assertEqual(body["status"], "CREATED")
        self.assertEqual(body["crmProvider"], "salesforce")
        self.assertEqual(body["modules"], ["Account", "Contact", "Opportunity"])
        self.assertEqual(body["reportContext"]["clock"], "CreatedDate")
        self.assertEqual(
            body["reportContext"]["organizationTimezone"], "America/Los_Angeles"
        )
        scan_row = datastore.tables["scan_jobs"].inserts[0]
        self.assertEqual(scan_row["crm_provider"], "salesforce")
        self.assertEqual(scan_row["clock_field"], "CreatedDate")
        self.assertEqual(scan_row["organization_timezone"], "America/Los_Angeles")
        self.assertEqual(scan_row["status"], "CREATED")
        self.assertNotIn("enqueue_orchestrate_scan", json.dumps(scan_row, default=str))
        self.enqueue.assert_called_once()
        enqueued_scan = self.enqueue.call_args[0][1]
        self.assertEqual(enqueued_scan["crm_provider"], "salesforce")
        self.assertEqual(enqueued_scan["ROWID"], scan_row["ROWID"])
        self.assertEqual(body["taskId"], "task_sf_test")
        self.assertEqual(body["taskStatus"], "QUEUED")
        self.assertTrue(body["workerSubmitted"])
        modules = datastore.tables["scan_module_runs"].inserts
        names = [row["module_api_name"] for row in modules]
        self.assertEqual(names, ["Account", "Contact", "Opportunity"])
        account = modules[0]
        allowlist = json.loads(account["field_allowlist_json"])
        metadata = json.loads(account["field_metadata_json"])
        self.assertIn("Id", allowlist)
        self.assertIn("CreatedDate", allowlist)
        self.assertNotIn("id", allowlist)
        self.assertNotIn("Created_Time", allowlist)
        self.assertEqual(metadata[0]["apiName"], "Id")
        self.assertNotIn("zoho_connections", zcql.queries)
        self.assertNotIn("zoho", json.dumps(scan_row, default=str).lower())
        self.directory_sync.assert_called_once()
        sync_args = self.directory_sync.call_args[0]
        self.assertIs(sync_args[0], datastore)
        self.assertIs(sync_args[1], zcql)
        self.assertEqual(sync_args[2], CONNECTION)
        self.assertEqual(sync_args[3], "stored-access-token")
        self.assertEqual(sync_args[4], "https://example.my.salesforce.com")
        self.assertNotIn("zoho_connection_users", datastore.table_names)

    def test_create_scan_syncs_owner_directory_like_zoho_discover(self):
        datastore = FakeDatastore()
        zcql = FakeZcql()
        with patch(
            "salesforce.client.get_salesforce_access_token",
            return_value=("stored-access-token", "https://example.my.salesforce.com"),
        ), patch(
            "salesforce.client.fetch_salesforce_organization",
            return_value={
                "id": "00D5g00000OrgIdAAA",
                "name": "Acme",
                "timeZone": "America/Los_Angeles",
            },
        ), patch(
            "salesforce.client.persist_salesforce_organization_name"
        ), patch(
            "salesforce.client.fetch_accessible_sobjects",
            return_value=[{"apiName": "Account", "label": "Account"}],
        ), patch(
            "salesforce.describe.fetch_sobject_describe",
            return_value=ACCOUNT_DESCRIBE,
        ), self.assertLogs("salesforce.scan_create", level="INFO") as logs:
            status, body = create_salesforce_scan(
                datastore, zcql, CONNECTION, PAYLOAD
            )
        self.assertEqual(status, 201)
        self.assertEqual(body["status"], "CREATED")
        self.assertTrue(
            any("SF_OWNER_DIR called=true connection_row_id=555" in message for message in logs.output)
        )
        self.directory_sync.assert_called_once_with(
            datastore,
            zcql,
            CONNECTION,
            "stored-access-token",
            "https://example.my.salesforce.com",
        )
        source = (
            Path(FUNCTION_ROOT) / "salesforce" / "scan_create.py"
        ).read_text(encoding="utf-8")
        self.assertIn("sync_salesforce_owner_directory", source)
        self.assertNotIn("sync_connection_user_directory", source)
        self.assertNotIn("zoho_connection_users", source)

    def test_owner_directory_sync_failure_does_not_block_scan_create(self):
        self.directory_sync.side_effect = RuntimeError("directory insert failed")
        with patch(
            "salesforce.client.get_salesforce_access_token",
            return_value=("stored-access-token", "https://example.my.salesforce.com"),
        ), patch(
            "salesforce.client.fetch_salesforce_organization",
            return_value={
                "id": "00D5g00000OrgIdAAA",
                "timeZone": "America/Los_Angeles",
            },
        ), patch(
            "salesforce.client.persist_salesforce_organization_name"
        ), patch(
            "salesforce.client.fetch_accessible_sobjects",
            return_value=[{"apiName": "Account", "label": "Account"}],
        ), patch(
            "salesforce.describe.fetch_sobject_describe",
            return_value=ACCOUNT_DESCRIBE,
        ), self.assertLogs("salesforce.scan_create", level="ERROR"):
            status, body = create_salesforce_scan(
                FakeDatastore(), FakeZcql(), CONNECTION, PAYLOAD
            )
        self.assertEqual(status, 201)
        self.assertEqual(body["status"], "CREATED")
        self.enqueue.assert_called_once()

    def test_modified_clock_stores_last_modified_date(self):
        datastore = FakeDatastore()
        with patch(
            "salesforce.client.get_salesforce_access_token",
            return_value=("stored-access-token", "https://example.my.salesforce.com"),
        ), patch(
            "salesforce.client.fetch_salesforce_organization",
            return_value={"id": "00D5g00000OrgIdAAA", "timeZone": "Asia/Kolkata"},
        ), patch(
            "salesforce.client.persist_salesforce_organization_name"
        ), patch(
            "salesforce.client.fetch_accessible_sobjects",
            return_value=[{"apiName": "Account", "label": "Account"}],
        ), patch(
            "salesforce.describe.fetch_sobject_describe",
            return_value=ACCOUNT_DESCRIBE,
        ):
            status, body = create_salesforce_scan(
                datastore,
                FakeZcql(),
                CONNECTION,
                {
                    "modules": ["Account"],
                    "depth": "quick",
                    "clock": "modified",
                    "range": {"id": "7d"},
                },
            )
        self.assertEqual(status, 201)
        self.assertEqual(body["reportContext"]["clock"], "LastModifiedDate")
        self.assertEqual(
            datastore.tables["scan_jobs"].inserts[0]["clock_field"], "LastModifiedDate"
        )

    def test_invalid_salesforce_objects_are_rejected(self):
        with patch(
            "salesforce.client.get_salesforce_access_token",
            return_value=("stored-access-token", "https://example.my.salesforce.com"),
        ), patch(
            "salesforce.client.fetch_salesforce_organization",
            return_value={"id": "00D5g00000OrgIdAAA", "timeZone": "America/Los_Angeles"},
        ), patch(
            "salesforce.client.persist_salesforce_organization_name"
        ), patch(
            "salesforce.client.fetch_accessible_sobjects",
            return_value=[{"apiName": "Account", "label": "Account"}],
        ):
            status, body = create_salesforce_scan(
                FakeDatastore(),
                FakeZcql(),
                CONNECTION,
                {
                    "modules": ["Accounts", "Deals"],
                    "depth": "quick",
                    "clock": "created",
                    "range": {"id": "7d"},
                },
            )
        self.assertEqual(status, 403)
        self.assertEqual(body["error"]["code"], "MODULE_NOT_ACCESSIBLE")
        self.enqueue.assert_not_called()

    def test_missing_timezone_fails_closed_on_create(self):
        with patch(
            "salesforce.client.get_salesforce_access_token",
            return_value=("stored-access-token", "https://example.my.salesforce.com"),
        ), patch(
            "salesforce.client.fetch_salesforce_organization",
            return_value={"id": "00D5g00000OrgIdAAA", "name": "Acme"},
        ), patch(
            "salesforce.client.persist_salesforce_organization_name"
        ):
            status, body = create_salesforce_scan(
                FakeDatastore(),
                FakeZcql(),
                CONNECTION,
                PAYLOAD,
            )
        self.assertEqual(status, 502)
        self.assertEqual(body["error"]["code"], "ORGANIZATION_TIMEZONE_MISSING")
        self.enqueue.assert_not_called()

    def test_create_does_not_enqueue_zoho_worker(self):
        source = (
            Path(FUNCTION_ROOT) / "salesforce" / "scan_create.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("enqueue_orchestrate_scan", source)
        self.assertNotIn("ANALYTICS_WORKER_JOB_POOL_NAME", source)
        self.assertNotIn("ai_data_analytics_worker", source)
        self.assertNotIn("zoho.client", source)
        self.assertNotIn("BASE_FIELD_ALLOWLIST", source)
        self.assertIn("_enqueue_salesforce_worker", source)
        self.assertIn("enqueue_salesforce_orchestrate_scan", source)
        self.assertIn('crm_provider": SALESFORCE_CRM_PROVIDER', source)
        routes = (Path(FUNCTION_ROOT) / "scans" / "routes.py").read_text(encoding="utf-8")
        self.assertIn("create_salesforce_scan", routes)
        self.assertIn("resolve_active_crm_connection", routes)
        self.assertNotIn("find_active_connection(", routes)
        self.assertIn("enqueue_orchestrate_scan", routes)
        self.assertIn("BASE_FIELD_ALLOWLIST", routes)
        after_sf = routes.split("if not connection_row:", 1)[1]
        self.assertIn("enqueue_orchestrate_scan", after_sf)
        self.assertIn("validate_scan_config(request.get_json(silent=True), connection_row)", after_sf)
        self.assertNotIn("enqueue_salesforce_orchestrate_scan", after_sf)

    def test_enqueue_failure_after_persist_is_not_silent_success(self):
        self.enqueue.return_value = {
            "ok": False,
            "code": "SALESFORCE_WORKER_TASK_CREATE_FAILED",
        }
        datastore = FakeDatastore()
        with patch(
            "salesforce.client.get_salesforce_access_token",
            return_value=("stored-access-token", "https://example.my.salesforce.com"),
        ), patch(
            "salesforce.client.fetch_salesforce_organization",
            return_value={"id": "00D5g00000OrgIdAAA", "timeZone": "America/Los_Angeles"},
        ), patch(
            "salesforce.client.persist_salesforce_organization_name"
        ), patch(
            "salesforce.client.fetch_accessible_sobjects",
            return_value=[{"apiName": "Account", "label": "Account"}],
        ), patch(
            "salesforce.describe.fetch_sobject_describe",
            return_value=ACCOUNT_DESCRIBE,
        ):
            status, body = create_salesforce_scan(
                datastore,
                FakeZcql(),
                CONNECTION,
                PAYLOAD,
            )
        self.assertEqual(status, 500)
        self.assertEqual(
            body["error"]["code"], "SALESFORCE_WORKER_TASK_CREATE_FAILED"
        )
        self.assertEqual(datastore.tables["scan_jobs"].inserts[0]["status"], "CREATED")
        self.assertEqual(body["scanId"], datastore.tables["scan_jobs"].inserts[0]["scan_id"])


class SalesforceScanOwnershipTests(unittest.TestCase):
    def test_owned_scan_uses_salesforce_connections_not_zoho(self):
        from analytics.repository import find_owned_scan
        from connections.repository import (
            find_persisted_scan_connection,
            find_scan_connection,
            scan_crm_provider,
        )

        scan = {
            "scan_id": "scan_abc",
            "crm_provider": "salesforce",
            "connection_row_id": "555",
        }
        self.assertEqual(scan_crm_provider(scan), "salesforce")
        self.assertIsNone(find_scan_connection(object(), "user-1", scan))
        self.assertIsNone(find_persisted_scan_connection(object(), scan))

        queries = []

        class Zcql:
            def execute_query(self, query):
                queries.append(query)
                if "from scan_jobs" in query:
                    return [{"scan_jobs": scan}]
                if "from salesforce_connections" in query:
                    return [
                        {
                            "salesforce_connections": {
                                "ROWID": "555",
                                "user_id": "user-1",
                            }
                        }
                    ]
                if "from zoho_connections" in query:
                    raise AssertionError(
                        "Salesforce ownership must not query zoho_connections"
                    )
                return []

        owned = find_owned_scan(Zcql(), "scan_abc", "user-1")
        self.assertEqual(owned["scan_id"], "scan_abc")
        self.assertTrue(any("salesforce_connections" in query for query in queries))
        self.assertFalse(any("zoho_connections" in query for query in queries))

    def test_another_users_salesforce_connection_is_not_owned(self):
        from analytics.repository import find_owned_scan

        scan = {
            "scan_id": "scan_abc",
            "crm_provider": "salesforce",
            "connection_row_id": "555",
        }

        class Zcql:
            def execute_query(self, query):
                if "from scan_jobs" in query:
                    return [{"scan_jobs": scan}]
                if "from salesforce_connections" in query:
                    return [
                        {
                            "salesforce_connections": {
                                "ROWID": "555",
                                "user_id": "user-1",
                            }
                        }
                    ]
                return []

        self.assertIsNone(find_owned_scan(Zcql(), "scan_abc", "user-2"))

    def test_zoho_scan_still_uses_zoho_connections(self):
        from analytics.repository import find_owned_scan

        scan = {"scan_id": "scan_zoho", "connection_row_id": "111"}
        queries = []

        class Zcql:
            def execute_query(self, query):
                queries.append(query)
                if "from scan_jobs" in query:
                    return [{"scan_jobs": scan}]
                if "from zoho_connections" in query:
                    return [
                        {"zoho_connections": {"ROWID": "111", "user_id": "user-1"}}
                    ]
                return []

        owned = find_owned_scan(Zcql(), "scan_zoho", "user-1")
        self.assertEqual(owned["scan_id"], "scan_zoho")
        self.assertTrue(any("zoho_connections" in query for query in queries))
        self.assertFalse(any("salesforce_connections" in query for query in queries))

    def test_discover_rejects_salesforce_extraction_and_advance_only_enqueues(self):
        discover = (Path(FUNCTION_ROOT) / "scans" / "discover.py").read_text(
            encoding="utf-8"
        )
        advance = (
            Path(FUNCTION_ROOT) / "orchestration" / "service.py"
        ).read_text(encoding="utf-8")
        self.assertIn("SALESFORCE_EXTRACTION_NOT_IMPLEMENTED", discover)
        self.assertNotIn("SALESFORCE_EXTRACTION_NOT_IMPLEMENTED", advance)
        self.assertIn("enqueue_salesforce_orchestrate_scan", advance)
        self.assertIn('scan_crm_provider(scan_row) == "salesforce"', discover)
        self.assertIn('scan_crm_provider(state["scan"]) == "salesforce"', advance)
        self.assertIn('"orchestrationOwner": "SALESFORCE_WORKER"', advance)
        zoho_enqueue = (
            Path(FUNCTION_ROOT) / "pipeline" / "orchestrate_enqueue.py"
        ).read_text(encoding="utf-8")
        self.assertIn("ANALYTICS_WORKER_JOB_POOL_NAME", zoho_enqueue)
        self.assertIn('ORCHESTRATE_TASK_TYPE = "ORCHESTRATE_SCAN"', zoho_enqueue)
        self.assertNotIn("SALESFORCE_WORKER_JOB_POOL_NAME", zoho_enqueue)


class SalesforceDescribeImportFix(unittest.TestCase):
    def test_describe_helpers_exist_or_local_fixtures_work(self):
        self.assertEqual(ACCOUNT_DESCRIBE["name"], "Account")
        self.assertEqual(CONTACT_DESCRIBE["name"], "Contact")
        self.assertEqual(OPPORTUNITY_DESCRIBE["name"], "Opportunity")


if __name__ == "__main__":
    unittest.main()
