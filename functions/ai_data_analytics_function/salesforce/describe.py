"""Salesforce sObject field describe and native field allowlisting."""

import logging
import re
from urllib.parse import quote, urlparse

logger = logging.getLogger(__name__)

SALESFORCE_BASE_FIELD_ALLOWLIST = ("Id", "CreatedDate", "LastModifiedDate")

# Salesforce-native quality names. Do not reuse Zoho QUALITY_FIELD_CANDIDATES.
SALESFORCE_QUALITY_FIELD_CANDIDATES = frozenset(
    {
        "Name",
        "FirstName",
        "LastName",
        "MiddleName",
        "Suffix",
        "Salutation",
        "Email",
        "Phone",
        "Fax",
        "MobilePhone",
        "HomePhone",
        "OtherPhone",
        "AssistantPhone",
        "Website",
        "Industry",
        "Type",
        "Rating",
        "BillingCountry",
        "BillingCity",
        "BillingState",
        "BillingPostalCode",
        "ShippingCountry",
        "ShippingCity",
        "ShippingState",
        "MailingCountry",
        "MailingCity",
        "MailingState",
        "MailingPostalCode",
        "OtherCountry",
        "AnnualRevenue",
        "NumberOfEmployees",
        "OwnerId",
        "CreatedById",
        "LastModifiedById",
        "AccountId",
        "ContactId",
        "ReportsToId",
        "ParentId",
        "StageName",
        "Amount",
        "CloseDate",
        "Probability",
        "ForecastCategory",
        "ForecastCategoryName",
        "LeadSource",
        "Status",
        "NextStep",
        "Title",
        "Department",
        "Description",
    }
)

SALESFORCE_QUALITY_FIELD_TYPES = frozenset(
    {
        "email",
        "phone",
        "url",
        "currency",
        "percent",
        "picklist",
        "multipicklist",
        "int",
        "double",
    }
)

SALESFORCE_QUALITY_REFERENCE_NAMES = frozenset(
    {
        "OwnerId",
        "CreatedById",
        "LastModifiedById",
        "AccountId",
        "ContactId",
        "ReportsToId",
        "ParentId",
    }
)

_NON_QUERYABLE_FIELD_TYPES = frozenset(
    {"address", "location", "base64", "complexvalue", "anyType"}
)

_EXCLUDED_FIELD_NAMES = frozenset(
    {
        "IsDeleted",
        "SystemModstamp",
        "MasterRecordId",
        "LastViewedDate",
        "LastReferencedDate",
        "LastActivityDate",
        "PhotoUrl",
    }
)

_SOBJECT_API_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,79}$")


def is_safe_sobject_api_name(value: str) -> bool:
    return bool(value and _SOBJECT_API_NAME.fullmatch(value))


def salesforce_describe_url(instance_url: str, object_api_name: str) -> str:
    parsed = urlparse(instance_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Salesforce instance URL is unavailable")
    # Keep in sync with salesforce.client.SALESFORCE_API_VERSION.
    api_version = "v62.0"
    encoded = quote(object_api_name, safe="")
    return (
        f"{instance_url.rstrip('/')}/services/data/{api_version}"
        f"/sobjects/{encoded}/describe"
    )


def _reference_to(field: dict) -> list:
    raw = field.get("referenceTo") or []
    if not isinstance(raw, list):
        return []
    names = []
    for item in raw:
        name = str(item or "").strip()
        if name:
            names.append(name)
    return names


def _optional_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_salesforce_field(field: dict) -> dict:
    """Map Salesforce describe metadata onto the scan field-discovery shape."""
    api_name = str(field.get("name") or "").strip()
    label = str(field.get("label") or api_name).strip() or api_name
    data_type = str(field.get("type") or "").strip()
    calculated = field.get("calculated") is True
    nillable = field.get("nillable")
    createable = field.get("createable") is True
    updateable = field.get("updateable") is True
    relationship = field.get("relationshipName")
    relationship_name = str(relationship).strip() if relationship else None
    return {
        "apiName": api_name,
        "label": label[:100],
        "dataType": data_type[:40],
        "systemMandatory": nillable is False and not calculated,
        "unique": field.get("unique") is True or field.get("externalId") is True,
        "readOnly": calculated or not (createable or updateable),
        "custom": field.get("custom") is True,
        "calculated": calculated,
        "filterable": field.get("filterable") is True,
        "referenceTo": _reference_to(field),
        "relationshipName": relationship_name,
        "restrictedPicklist": field.get("restrictedPicklist") is True,
        "length": _optional_int(field.get("length")),
    }


def is_salesforce_field_usable(field: dict) -> bool:
    """Drop hidden, compound, binary, and explicitly non-queryable fields."""
    api_name = str(field.get("name") or "").strip()
    if not api_name:
        return False
    if field.get("deprecatedAndHidden") is True:
        return False
    if field.get("queryable") is False:
        return False
    data_type = str(field.get("type") or "").strip()
    if data_type in _NON_QUERYABLE_FIELD_TYPES:
        return False
    return True


def is_salesforce_quality_field(field: dict) -> bool:
    api_name = str(field.get("name") or "").strip()
    if not api_name or api_name in _EXCLUDED_FIELD_NAMES:
        return False
    if api_name in SALESFORCE_QUALITY_FIELD_CANDIDATES:
        return True
    if field.get("nameField") is True:
        return True
    if field.get("unique") is True or field.get("externalId") is True:
        return True
    if field.get("nillable") is False and field.get("calculated") is not True:
        return True
    data_type = str(field.get("type") or "").strip()
    if data_type in SALESFORCE_QUALITY_FIELD_TYPES:
        return True
    if data_type in {"date", "datetime"} and field.get("custom") is True:
        return True
    if data_type == "reference" and (
        api_name in SALESFORCE_QUALITY_REFERENCE_NAMES or api_name.endswith("__c")
    ):
        return True
    extra = str(field.get("extraTypeInfo") or "").strip().lower()
    if extra in {"email", "personname"} and data_type in {"string", "textarea"}:
        return True
    return False


def build_salesforce_field_allowlist(fields: list) -> list:
    """Select readable Salesforce fields without assuming a shared object schema."""
    present = {}
    for field in fields:
        if not isinstance(field, dict):
            continue
        api_name = str(field.get("name") or "").strip()
        if api_name:
            present[api_name] = field

    selected = []
    selected_names = set()
    for api_name in SALESFORCE_BASE_FIELD_ALLOWLIST:
        field = present.get(api_name)
        if field and is_salesforce_field_usable(field):
            selected.append(api_name)
            selected_names.add(api_name)

    extras = []
    for field in fields:
        if not isinstance(field, dict):
            continue
        api_name = str(field.get("name") or "").strip()
        if not api_name or api_name in selected_names:
            continue
        if not is_salesforce_field_usable(field):
            continue
        if is_salesforce_quality_field(field):
            extras.append(api_name)
            selected_names.add(api_name)
    extras.sort()
    return [*selected, *extras]


def build_salesforce_field_metadata(fields: list, allowlist: list) -> list:
    """Retain scan-discovery field properties plus Salesforce-specific extras."""
    fields_by_name = {}
    for field in fields:
        if not isinstance(field, dict):
            continue
        api_name = str(field.get("name") or "").strip()
        if api_name:
            fields_by_name[api_name] = field
    metadata = []
    for api_name in allowlist:
        field = fields_by_name.get(api_name)
        if not field:
            continue
        metadata.append(normalize_salesforce_field(field))
    return metadata


def describe_salesforce_fields(describe_payload: dict) -> dict:
    fields = describe_payload.get("fields") or []
    if not isinstance(fields, list):
        fields = []
    allowlist = build_salesforce_field_allowlist(fields)
    object_api_name = str(describe_payload.get("name") or "").strip()
    label = str(describe_payload.get("label") or object_api_name).strip() or object_api_name
    return {
        "object": {
            "apiName": object_api_name,
            "label": label,
            "custom": describe_payload.get("custom") is True,
            "queryable": describe_payload.get("queryable") is True,
        },
        "allowlist": allowlist,
        "fields": build_salesforce_field_metadata(fields, allowlist),
    }


def _salesforce_authorized_get(url, access_token, params=None, timeout=20):
    from salesforce.client import _authorized_get

    return _authorized_get(url, access_token, params=params, timeout=timeout)


def _describe_error(code, message, cause=None):
    from common.core import DiscoveryError

    error = DiscoveryError(code, message)
    if cause is not None:
        raise error from cause
    raise error


def fetch_sobject_describe(access_token: str, instance_url: str, object_api_name: str):
    """GET /sobjects/{ObjectApiName}/describe using a stored-connection token."""
    import requests

    if not is_safe_sobject_api_name(object_api_name):
        _describe_error(
            "INVALID_OBJECT_API_NAME", "Salesforce object name is invalid"
        )
    try:
        url = salesforce_describe_url(instance_url, object_api_name)
    except ValueError as exc:
        _describe_error("SALESFORCE_INSTANCE_MISSING", str(exc), exc)

    try:
        payload = _salesforce_authorized_get(url, access_token, timeout=20)
    except requests.HTTPError as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status == 404:
            _describe_error(
                "OBJECT_NOT_FOUND",
                f"Salesforce object {object_api_name} was not found",
                exc,
            )
        logger.warning(
            "Salesforce describe failed for object %s: status=%s",
            object_api_name,
            status,
        )
        _describe_error(
            "FIELD_DISCOVERY_FAILED",
            f"Could not read field metadata for {object_api_name}",
            exc,
        )
    except (requests.RequestException, ValueError, TypeError) as exc:
        logger.warning(
            "Salesforce describe failed for object %s: %s",
            object_api_name,
            type(exc).__name__,
        )
        _describe_error(
            "FIELD_DISCOVERY_FAILED",
            f"Could not read field metadata for {object_api_name}",
            exc,
        )

    if not isinstance(payload, dict):
        _describe_error(
            "FIELD_DISCOVERY_FAILED",
            f"Could not read field metadata for {object_api_name}",
        )
    return payload


def get_salesforce_object_describe(request, datastore, object_api_name: str):
    import zcatalyst_sdk

    from common.core import DiscoveryError, get_current_user_id, json_response
    from salesforce.client import get_salesforce_access_token
    from salesforce.oauth import (
        find_active_salesforce_connection,
        find_connected_salesforce_connection,
    )

    if not is_safe_sobject_api_name(object_api_name):
        return json_response(
            {
                "error": {
                    "code": "INVALID_OBJECT_API_NAME",
                    "message": "Salesforce object name is invalid",
                }
            },
            400,
        )

    user_id = get_current_user_id(request)
    zcql = zcatalyst_sdk.initialize().zcql()
    row = find_active_salesforce_connection(
        zcql, user_id
    ) or find_connected_salesforce_connection(zcql, user_id)
    if not row:
        return json_response(
            {
                "error": {
                    "code": "SALESFORCE_CONNECTION_REQUIRED",
                    "message": "Connect Salesforce CRM",
                }
            },
            409,
        )

    try:
        access_token, instance_url = get_salesforce_access_token(datastore, row)
        payload = fetch_sobject_describe(access_token, instance_url, object_api_name)
        described = describe_salesforce_fields(payload)
    except DiscoveryError as exc:
        logger.exception(
            "Salesforce field describe failed for user %s object %s with %s",
            user_id,
            object_api_name,
            exc.code,
        )
        status = 404 if exc.code == "OBJECT_NOT_FOUND" else 502
        return json_response(
            {"error": {"code": exc.code, "message": str(exc)}},
            status,
        )
    except Exception:  # noqa: BLE001 - keep provider details server-side
        logger.exception(
            "Unexpected Salesforce field describe failure for user %s object %s",
            user_id,
            object_api_name,
        )
        return json_response(
            {
                "error": {
                    "code": "SALESFORCE_DESCRIBE_FAILED",
                    "message": "Salesforce field metadata could not be read",
                }
            },
            500,
        )

    return json_response(
        {
            "connectionId": str(row["ROWID"]),
            "object": described["object"],
            "allowlist": described["allowlist"],
            "fields": described["fields"],
        }
    )
