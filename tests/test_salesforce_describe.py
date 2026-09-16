import sys
import unittest
from pathlib import Path


FUNCTION_ROOT = (
    Path(__file__).resolve().parents[1]
    / "functions"
    / "ai_data_analytics_function"
)
sys.path.insert(0, str(FUNCTION_ROOT))

from salesforce.describe import (
    SALESFORCE_BASE_FIELD_ALLOWLIST,
    build_salesforce_field_allowlist,
    build_salesforce_field_metadata,
    describe_salesforce_fields,
    is_safe_sobject_api_name,
    normalize_salesforce_field,
)


def describe_field(name, field_type="string", **overrides):
    field = {
        "name": name,
        "label": overrides.pop("label", name),
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
        label="Record ID",
        nillable=False,
        unique=True,
        createable=False,
        updateable=False,
        length=18,
        custom=False,
    )


def created_date_field():
    return describe_field(
        "CreatedDate",
        "datetime",
        label="Created Date",
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
        label="Last Modified Date",
        nillable=False,
        createable=False,
        updateable=False,
        custom=False,
        length=0,
    )


def owner_id_field(reference_to="User"):
    return describe_field(
        "OwnerId",
        "reference",
        label="Owner ID",
        nillable=False,
        custom=False,
        length=18,
        referenceTo=[reference_to, "Group"],
        relationshipName="Owner",
    )


ACCOUNT_DESCRIBE = {
    "name": "Account",
    "label": "Account",
    "custom": False,
    "queryable": True,
    "fields": [
        id_field(),
        created_date_field(),
        last_modified_date_field(),
        describe_field(
            "Name",
            "string",
            label="Account Name",
            nillable=False,
            nameField=True,
            custom=False,
            length=255,
        ),
        describe_field("Phone", "phone", custom=False, length=40),
        describe_field("Website", "url", custom=False, length=255),
        describe_field(
            "Industry",
            "picklist",
            custom=False,
            restrictedPicklist=False,
            length=40,
        ),
        describe_field("Type", "picklist", custom=False, length=40),
        describe_field(
            "AnnualRevenue",
            "currency",
            label="Annual Revenue",
            custom=False,
            length=0,
        ),
        describe_field(
            "NumberOfEmployees",
            "int",
            label="Employees",
            custom=False,
            length=0,
        ),
        describe_field(
            "BillingCountry",
            "string",
            label="Billing Country",
            custom=False,
            compoundFieldName="BillingAddress",
        ),
        describe_field(
            "BillingAddress",
            "address",
            label="Billing Address",
            custom=False,
            filterable=False,
            updateable=False,
            createable=False,
        ),
        owner_id_field(),
        describe_field(
            "IsDeleted",
            "boolean",
            nillable=False,
            createable=False,
            updateable=False,
            custom=False,
        ),
        describe_field(
            "SystemModstamp",
            "datetime",
            nillable=False,
            createable=False,
            updateable=False,
            custom=False,
        ),
        describe_field(
            "PhotoUrl",
            "url",
            createable=False,
            updateable=False,
            custom=False,
        ),
        describe_field(
            "HiddenNotes",
            "textarea",
            deprecatedAndHidden=True,
            custom=False,
        ),
        describe_field(
            "InternalBlob",
            "base64",
            filterable=False,
            custom=False,
        ),
        describe_field(
            "Description",
            "textarea",
            custom=False,
            filterable=False,
            length=32000,
        ),
    ],
}

CONTACT_DESCRIBE = {
    "name": "Contact",
    "label": "Contact",
    "custom": False,
    "queryable": True,
    "fields": [
        id_field(),
        created_date_field(),
        last_modified_date_field(),
        describe_field(
            "Name",
            "string",
            label="Full Name",
            nillable=False,
            nameField=True,
            createable=False,
            updateable=False,
            custom=False,
        ),
        describe_field("FirstName", "string", custom=False),
        describe_field(
            "LastName",
            "string",
            nillable=False,
            custom=False,
        ),
        describe_field("Email", "email", custom=False, length=80),
        describe_field("Phone", "phone", custom=False, length=40),
        describe_field("MobilePhone", "phone", custom=False, length=40),
        describe_field(
            "AccountId",
            "reference",
            label="Account ID",
            custom=False,
            length=18,
            referenceTo=["Account"],
            relationshipName="Account",
        ),
        owner_id_field(),
        describe_field(
            "MailingCountry",
            "string",
            label="Mailing Country",
            custom=False,
        ),
        describe_field(
            "MailingAddress",
            "address",
            label="Mailing Address",
            custom=False,
            filterable=False,
            createable=False,
            updateable=False,
        ),
        describe_field(
            "LeadSource",
            "picklist",
            custom=False,
            restrictedPicklist=False,
        ),
        describe_field(
            "Title",
            "string",
            custom=False,
        ),
        describe_field(
            "EncryptedSSN",
            "string",
            queryable=False,
            filterable=False,
            custom=False,
        ),
    ],
}

OPPORTUNITY_DESCRIBE = {
    "name": "Opportunity",
    "label": "Opportunity",
    "custom": False,
    "queryable": True,
    "fields": [
        id_field(),
        created_date_field(),
        last_modified_date_field(),
        describe_field(
            "Name",
            "string",
            label="Opportunity Name",
            nillable=False,
            nameField=True,
            custom=False,
        ),
        describe_field(
            "StageName",
            "picklist",
            label="Stage",
            nillable=False,
            custom=False,
            restrictedPicklist=True,
            length=40,
        ),
        describe_field(
            "CloseDate",
            "date",
            label="Close Date",
            nillable=False,
            custom=False,
            length=0,
        ),
        describe_field(
            "Amount",
            "currency",
            custom=False,
            length=0,
        ),
        describe_field(
            "Probability",
            "percent",
            custom=False,
            length=0,
        ),
        describe_field(
            "AccountId",
            "reference",
            custom=False,
            length=18,
            referenceTo=["Account"],
            relationshipName="Account",
        ),
        owner_id_field(),
        describe_field(
            "ForecastCategoryName",
            "picklist",
            custom=False,
            createable=False,
            restrictedPicklist=True,
        ),
        describe_field(
            "ExpectedRevenue",
            "currency",
            calculated=True,
            createable=False,
            updateable=False,
            custom=False,
            length=0,
        ),
        describe_field("LeadSource", "picklist", custom=False),
        describe_field("Type", "picklist", custom=False),
        describe_field("NextStep", "string", custom=False),
        describe_field(
            "LastViewedDate",
            "datetime",
            createable=False,
            updateable=False,
            custom=False,
        ),
    ],
}

INVOICE_DESCRIBE = {
    "name": "Invoice__c",
    "label": "Invoice",
    "custom": True,
    "queryable": True,
    "fields": [
        id_field(),
        created_date_field(),
        last_modified_date_field(),
        describe_field(
            "Name",
            "string",
            label="Invoice Number",
            nillable=False,
            nameField=True,
            custom=True,
        ),
        describe_field(
            "Amount__c",
            "currency",
            label="Amount",
            nillable=False,
            length=0,
        ),
        describe_field(
            "Status__c",
            "picklist",
            label="Status",
            restrictedPicklist=True,
            length=40,
        ),
        describe_field(
            "Account__c",
            "reference",
            label="Account",
            length=18,
            referenceTo=["Account"],
            relationshipName="Account__r",
        ),
        describe_field("Email__c", "email", label="Billing Email", length=80),
        describe_field("Phone__c", "phone", label="Billing Phone", length=40),
        describe_field(
            "Unique_Code__c",
            "string",
            label="Unique Code",
            unique=True,
            externalId=True,
            length=20,
        ),
        describe_field(
            "Balance__c",
            "currency",
            label="Balance",
            calculated=True,
            createable=False,
            updateable=False,
            length=0,
        ),
        describe_field(
            "Due_Date__c",
            "date",
            label="Due Date",
            length=0,
        ),
        describe_field(
            "Notes__c",
            "textarea",
            label="Internal Notes",
            filterable=False,
        ),
        describe_field(
            "Location__c",
            "location",
            label="Warehouse",
            filterable=False,
            createable=False,
            updateable=False,
        ),
        describe_field(
            "Attachment__c",
            "base64",
            label="Attachment",
            filterable=False,
        ),
        describe_field(
            "Secret_Key__c",
            "string",
            deprecatedAndHidden=True,
        ),
        describe_field(
            "Hidden_Score__c",
            "double",
            queryable=False,
            filterable=False,
        ),
        owner_id_field(),
    ],
}


def allowlist_for(payload):
    return build_salesforce_field_allowlist(payload["fields"])


def metadata_by_name(payload):
    allowlist = allowlist_for(payload)
    return {
        item["apiName"]: item
        for item in build_salesforce_field_metadata(payload["fields"], allowlist)
    }


class SalesforceDescribeNameTests(unittest.TestCase):
    def test_accepts_standard_and_custom_api_names(self):
        self.assertTrue(is_safe_sobject_api_name("Account"))
        self.assertTrue(is_safe_sobject_api_name("Invoice__c"))
        self.assertTrue(is_safe_sobject_api_name("ns__Invoice__c"))
        self.assertFalse(is_safe_sobject_api_name("../Account"))
        self.assertFalse(is_safe_sobject_api_name("Account/describe"))
        self.assertFalse(is_safe_sobject_api_name(""))


class SalesforceFieldNormalizationTests(unittest.TestCase):
    def test_preserves_salesforce_api_names(self):
        normalized = normalize_salesforce_field(
            describe_field(
                "CreatedDate",
                "datetime",
                nillable=False,
                createable=False,
                updateable=False,
                custom=False,
            )
        )
        self.assertEqual(normalized["apiName"], "CreatedDate")
        self.assertEqual(normalized["dataType"], "datetime")
        self.assertTrue(normalized["systemMandatory"])
        self.assertTrue(normalized["readOnly"])
        self.assertFalse(normalized["custom"])

    def test_maps_required_unique_calculated_and_reference_metadata(self):
        normalized = normalize_salesforce_field(
            describe_field(
                "Account__c",
                "reference",
                nillable=False,
                unique=True,
                calculated=False,
                referenceTo=["Account"],
                relationshipName="Account__r",
                restrictedPicklist=False,
                length=18,
            )
        )
        self.assertEqual(
            normalized,
            {
                "apiName": "Account__c",
                "label": "Account__c",
                "dataType": "reference",
                "systemMandatory": True,
                "unique": True,
                "readOnly": False,
                "custom": True,
                "calculated": False,
                "filterable": True,
                "referenceTo": ["Account"],
                "relationshipName": "Account__r",
                "restrictedPicklist": False,
                "length": 18,
            },
        )

    def test_formula_fields_are_read_only_and_not_system_mandatory(self):
        normalized = normalize_salesforce_field(
            describe_field(
                "Balance__c",
                "currency",
                calculated=True,
                nillable=False,
                createable=False,
                updateable=False,
            )
        )
        self.assertTrue(normalized["calculated"])
        self.assertTrue(normalized["readOnly"])
        self.assertFalse(normalized["systemMandatory"])


class SalesforceAllowlistContractTests(unittest.TestCase):
    def test_does_not_reuse_zoho_field_names_or_candidates(self):
        source = (
            Path(FUNCTION_ROOT) / "salesforce" / "describe.py"
        ).read_text(encoding="utf-8")
        self.assertIn("SALESFORCE_QUALITY_FIELD_CANDIDATES", source)
        self.assertNotIn("Created_Time", source)
        self.assertNotIn("Modified_Time", source)
        self.assertNotIn("from zoho", source)
        self.assertNotIn("import zoho", source)
        self.assertNotIn(
            "from common.core import",
            source.split("def _describe_error")[0],
        )

    def test_clock_and_id_fields_are_first_when_present(self):
        allowlist = allowlist_for(ACCOUNT_DESCRIBE)
        self.assertEqual(
            allowlist[:3],
            list(SALESFORCE_BASE_FIELD_ALLOWLIST),
        )


class AccountDescribeTests(unittest.TestCase):
    def test_includes_id_clock_contact_quality_and_owner(self):
        allowlist = allowlist_for(ACCOUNT_DESCRIBE)
        for name in (
            "Id",
            "CreatedDate",
            "LastModifiedDate",
            "Name",
            "Phone",
            "Website",
            "Industry",
            "AnnualRevenue",
            "OwnerId",
            "BillingCountry",
        ):
            self.assertIn(name, allowlist)

    def test_excludes_compound_hidden_and_system_noise(self):
        allowlist = allowlist_for(ACCOUNT_DESCRIBE)
        for name in (
            "BillingAddress",
            "HiddenNotes",
            "InternalBlob",
            "IsDeleted",
            "SystemModstamp",
            "PhotoUrl",
        ):
            self.assertNotIn(name, allowlist)

    def test_keeps_salesforce_names_not_zoho_aliases(self):
        allowlist = allowlist_for(ACCOUNT_DESCRIBE)
        self.assertIn("CreatedDate", allowlist)
        self.assertNotIn("Created_Time", allowlist)
        self.assertIn("OwnerId", allowlist)
        self.assertNotIn("Owner", allowlist)

    def test_phone_currency_and_picklist_metadata(self):
        by_name = metadata_by_name(ACCOUNT_DESCRIBE)
        self.assertEqual(by_name["Phone"]["dataType"], "phone")
        self.assertEqual(by_name["AnnualRevenue"]["dataType"], "currency")
        self.assertEqual(by_name["Industry"]["dataType"], "picklist")
        self.assertFalse(by_name["Industry"]["restrictedPicklist"])
        self.assertEqual(by_name["OwnerId"]["referenceTo"], ["User", "Group"])
        self.assertEqual(by_name["OwnerId"]["relationshipName"], "Owner")
        self.assertTrue(by_name["Name"]["systemMandatory"])


class ContactDescribeTests(unittest.TestCase):
    def test_includes_email_phone_and_account_lookup(self):
        allowlist = allowlist_for(CONTACT_DESCRIBE)
        for name in (
            "Id",
            "CreatedDate",
            "LastModifiedDate",
            "Email",
            "Phone",
            "MobilePhone",
            "AccountId",
            "LastName",
            "MailingCountry",
            "LeadSource",
        ):
            self.assertIn(name, allowlist)

    def test_excludes_compound_address_and_unreadable_fields(self):
        allowlist = allowlist_for(CONTACT_DESCRIBE)
        self.assertNotIn("MailingAddress", allowlist)
        self.assertNotIn("EncryptedSSN", allowlist)

    def test_email_and_reference_shape(self):
        by_name = metadata_by_name(CONTACT_DESCRIBE)
        self.assertEqual(by_name["Email"]["dataType"], "email")
        self.assertEqual(by_name["AccountId"]["dataType"], "reference")
        self.assertEqual(by_name["AccountId"]["referenceTo"], ["Account"])
        self.assertTrue(by_name["LastName"]["systemMandatory"])
        self.assertTrue(by_name["Name"]["readOnly"])


class OpportunityDescribeTests(unittest.TestCase):
    def test_includes_stage_amount_close_date_and_formula_currency(self):
        allowlist = allowlist_for(OPPORTUNITY_DESCRIBE)
        for name in (
            "Id",
            "CreatedDate",
            "LastModifiedDate",
            "StageName",
            "Amount",
            "CloseDate",
            "Probability",
            "AccountId",
            "OwnerId",
            "ExpectedRevenue",
        ):
            self.assertIn(name, allowlist)
        self.assertNotIn("LastViewedDate", allowlist)
        self.assertNotIn("Stage", allowlist)
        self.assertNotIn("Closing_Date", allowlist)

    def test_picklist_currency_required_and_calculated_metadata(self):
        by_name = metadata_by_name(OPPORTUNITY_DESCRIBE)
        self.assertEqual(by_name["StageName"]["dataType"], "picklist")
        self.assertTrue(by_name["StageName"]["restrictedPicklist"])
        self.assertTrue(by_name["StageName"]["systemMandatory"])
        self.assertEqual(by_name["Amount"]["dataType"], "currency")
        self.assertEqual(by_name["CloseDate"]["apiName"], "CloseDate")
        self.assertTrue(by_name["CloseDate"]["systemMandatory"])
        self.assertTrue(by_name["ExpectedRevenue"]["calculated"])
        self.assertTrue(by_name["ExpectedRevenue"]["readOnly"])
        self.assertFalse(by_name["ExpectedRevenue"]["systemMandatory"])


class InvoiceCustomObjectDescribeTests(unittest.TestCase):
    def test_includes_custom_quality_fields_without_assuming_standard_schema(self):
        allowlist = allowlist_for(INVOICE_DESCRIBE)
        for name in (
            "Id",
            "CreatedDate",
            "LastModifiedDate",
            "Name",
            "Amount__c",
            "Status__c",
            "Account__c",
            "Email__c",
            "Phone__c",
            "Unique_Code__c",
            "Balance__c",
            "Due_Date__c",
            "OwnerId",
        ):
            self.assertIn(name, allowlist)
        self.assertNotIn("Notes__c", allowlist)
        self.assertNotIn("Location__c", allowlist)
        self.assertNotIn("Attachment__c", allowlist)
        self.assertNotIn("Secret_Key__c", allowlist)
        self.assertNotIn("Hidden_Score__c", allowlist)

    def test_custom_object_metadata_keeps_salesforce_api_names(self):
        described = describe_salesforce_fields(INVOICE_DESCRIBE)
        self.assertEqual(described["object"]["apiName"], "Invoice__c")
        self.assertTrue(described["object"]["custom"])
        by_name = {item["apiName"]: item for item in described["fields"]}
        self.assertTrue(by_name["Unique_Code__c"]["unique"])
        self.assertTrue(by_name["Amount__c"]["systemMandatory"])
        self.assertEqual(by_name["Account__c"]["referenceTo"], ["Account"])
        self.assertEqual(by_name["Account__c"]["relationshipName"], "Account__r")
        self.assertTrue(by_name["Balance__c"]["calculated"])
        self.assertEqual(by_name["Status__c"]["dataType"], "picklist")
        self.assertEqual(by_name["Email__c"]["dataType"], "email")
        self.assertEqual(by_name["Phone__c"]["dataType"], "phone")
        self.assertEqual(described["fields"][0]["apiName"], "Id")


class SalesforceDescribeResponseContractTests(unittest.TestCase):
    def test_metadata_uses_existing_scan_field_keys(self):
        fields = build_salesforce_field_metadata(
            ACCOUNT_DESCRIBE["fields"],
            allowlist_for(ACCOUNT_DESCRIBE),
        )
        required = {
            "apiName",
            "label",
            "dataType",
            "systemMandatory",
            "unique",
            "readOnly",
            "custom",
        }
        extras = {
            "calculated",
            "filterable",
            "referenceTo",
            "relationshipName",
            "restrictedPicklist",
            "length",
        }
        for field in fields:
            self.assertTrue(required.issubset(field))
            self.assertTrue(extras.issubset(field))


class SalesforceDescribeFetchTests(unittest.TestCase):
    def test_describe_url_targets_object_describe_endpoint(self):
        from salesforce.describe import salesforce_describe_url

        url = salesforce_describe_url(
            "https://example.my.salesforce.com", "Invoice__c"
        )
        self.assertEqual(
            url,
            "https://example.my.salesforce.com/services/data/v62.0/sobjects/Invoice__c/describe",
        )

    def test_fetch_uses_stored_token_and_does_not_accept_client_tokens(self):
        from unittest.mock import patch

        from salesforce.describe import fetch_sobject_describe

        try:
            with patch(
                "salesforce.describe._salesforce_authorized_get",
                return_value=ACCOUNT_DESCRIBE,
            ) as authorized_get:
                payload = fetch_sobject_describe(
                    "stored-access-token",
                    "https://example.my.salesforce.com",
                    "Account",
                )
        except ImportError as exc:
            if "flask" in str(exc).lower():
                self.skipTest("flask is not installed in the test environment")
            raise
        self.assertEqual(payload["name"], "Account")
        authorized_get.assert_called_once()
        args, kwargs = authorized_get.call_args
        self.assertIn("/sobjects/Account/describe", args[0])
        self.assertEqual(args[1], "stored-access-token")
        self.assertNotIn("access_token", kwargs)


if __name__ == "__main__":
    unittest.main()
