"""Read-only Salesforce organization and object metadata."""

import logging
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

SALESFORCE_API_VERSION = "v62.0"
SALESFORCE_ORGANIZATION_QUERY = (
    "SELECT Id, Name, TimeZoneSidKey, IsSandbox, OrganizationType FROM Organization"
)
# Keep in sync with salesforce.oauth; duplicated so this module stays importable
# without Flask for token-persistence unit tests.
SALESFORCE_CONNECTIONS_TABLE = "salesforce_connections"
DEFAULT_ACCESS_TOKEN_SECONDS = 7200

# Associated/system artifacts that describeGlobal still returns as queryable.
_EXCLUDED_NAME_SUFFIXES = (
    "ChangeEvent",
    "ChangeEventHeader",
    "Feed",
    "History",
    "OwnerSharingRule",
    "Share",
    "Tag",
    "__Feed",
    "__History",
    "__Share",
    "__b",
    "__chn",
    "__e",
    "__hd",
    "__mdt",
    "__x",
)

# Layoutable or queryable setup/identity objects that are not CRM scan targets.
_EXCLUDED_STANDARD_OBJECTS = frozenset(
    {
        "ApexClass",
        "ApexComponent",
        "ApexLog",
        "ApexPage",
        "ApexTrigger",
        "AsyncApexJob",
        "Attachment",
        "AuthSession",
        "BusinessProcess",
        "ContentDocument",
        "ContentDocumentLink",
        "ContentVersion",
        "CronJobDetail",
        "CronTrigger",
        "Document",
        "EmailTemplate",
        "FieldPermissions",
        "Folder",
        "Group",
        "GroupMember",
        "LoginHistory",
        "Note",
        "ObjectPermissions",
        "Organization",
        "PackageLicense",
        "PermissionSet",
        "PermissionSetAssignment",
        "PermissionSetGroup",
        "PermissionSetLicense",
        "Profile",
        "QueueSobject",
        "RecordType",
        "SetupEntityAccess",
        "StaticResource",
        "User",
        "UserLicense",
        "UserRole",
        "ValidationRule",
        "WebLink",
    }
)


def _discovery_error(code, message, cause=None):
    try:
        from common.core import DiscoveryError
    except ImportError:
        class DiscoveryError(RuntimeError):
            def __init__(self, error_code, error_message):
                super().__init__(error_message)
                self.code = error_code

    error = DiscoveryError(code, message)
    if cause is not None:
        raise error from cause
    raise error


def _login_url():
    value = str(os.environ.get("SALESFORCE_LOGIN_URL") or "").strip().rstrip("/")
    if not value.startswith("https://"):
        _discovery_error(
            "SALESFORCE_OAUTH_CONFIG", "Salesforce OAuth is not configured"
        )
    return value


def _salesforce_error_summary(response):
    try:
        payload = response.json()
    except ValueError:
        return f"status={response.status_code}"
    if isinstance(payload, list) and payload:
        first = payload[0] if isinstance(payload[0], dict) else {}
        code = first.get("errorCode") or first.get("error") or ""
        return f"status={response.status_code} errorCode={code}"
    if isinstance(payload, dict):
        code = payload.get("errorCode") or payload.get("error") or ""
        return f"status={response.status_code} errorCode={code}"
    return f"status={response.status_code}"


def _instance_url(connection_row: dict) -> str:
    value = str(connection_row.get("instance_url") or "").strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        _discovery_error(
            "SALESFORCE_INSTANCE_MISSING",
            "Salesforce instance URL is unavailable",
        )
    return value


def _https_instance_url(value: str, fallback: str) -> str:
    candidate = str(value or "").strip().rstrip("/")
    parsed = urlparse(candidate)
    if parsed.scheme == "https" and parsed.netloc:
        return candidate
    return fallback


def _token_expiry_value(now: datetime, expires_in: int) -> str:
    expires_at = now + timedelta(seconds=expires_in)
    return expires_at.strftime("%Y-%m-%d %H:%M:%S:%f")[:-3]


def _parse_token_expiry(value: str) -> datetime:
    for date_format in ("%Y-%m-%d %H:%M:%S:%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, date_format).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError("Unsupported Catalyst DateTime value")


def build_salesforce_token_update(connection_row: dict, token_data: dict, now=None):
    """Build the Data Store row update for a successful Salesforce token refresh.

    Salesforce Refresh Token Rotation may return a new refresh_token. Persist it
    only when present; omit the column otherwise so the stored value is retained.
    Never call this for a failed refresh payload.
    """
    if not isinstance(token_data, dict) or token_data.get("error"):
        raise ValueError("Salesforce token refresh payload is not usable")
    access_token = token_data.get("access_token")
    if not access_token:
        raise ValueError("Salesforce token refresh payload is not usable")

    current_instance = str(connection_row.get("instance_url") or "").rstrip("/")
    next_instance = _https_instance_url(
        token_data.get("instance_url"), current_instance
    )
    raw_expires = token_data.get("expires_in")
    try:
        expires_in = int(raw_expires or DEFAULT_ACCESS_TOKEN_SECONDS)
    except (TypeError, ValueError):
        expires_in = DEFAULT_ACCESS_TOKEN_SECONDS
    update = {
        "ROWID": connection_row["ROWID"],
        "access_token": access_token,
        "token_expires_at": _token_expiry_value(
            now or datetime.now(timezone.utc), expires_in
        ),
        "instance_url": next_instance,
    }
    rotated_refresh = str(token_data.get("refresh_token") or "").strip()
    if rotated_refresh:
        update["refresh_token"] = rotated_refresh
    return update


def persist_salesforce_token_refresh(
    datastore, connection_row: dict, token_data: dict, now=None
):
    """Persist a successful refresh. Must not be called for failed responses."""
    update = build_salesforce_token_update(connection_row, token_data, now=now)
    datastore.table(SALESFORCE_CONNECTIONS_TABLE).update_row(update)
    connection_row.update(update)
    return update


def get_salesforce_access_token(datastore, connection_row: dict):
    """Return a usable access token and instance URL from the stored connection.

    Concurrent refresh of the same row is not serialized. Catalyst Data Store
    update_row is last-write-wins and has no compare-and-set, so two overlapping
    refreshes can rotate the same refresh-token family. A connection-scoped lock
    would need a new schema/lease design and is not implemented here.
    """
    instance_url = _instance_url(connection_row)
    expires_at_value = connection_row.get("token_expires_at")
    if expires_at_value:
        try:
            expires_at = _parse_token_expiry(str(expires_at_value))
            if expires_at > datetime.now(timezone.utc) + timedelta(minutes=5):
                return connection_row["access_token"], instance_url
        except ValueError:
            logger.warning("Stored Salesforce token expiry could not be parsed; refreshing")

    refresh_token = connection_row.get("refresh_token")
    if not refresh_token:
        _discovery_error("REFRESH_TOKEN_MISSING", "Reconnect Salesforce CRM")

    try:
        response = requests.post(
            f"{_login_url()}/services/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "client_id": os.environ["SALESFORCE_CLIENT_ID"],
                "client_secret": os.environ["SALESFORCE_CLIENT_SECRET"],
                "refresh_token": refresh_token,
            },
            timeout=15,
        )
        response.raise_for_status()
        token_data = response.json()
    except (requests.RequestException, ValueError, KeyError) as exc:
        logger.warning("Salesforce token refresh failed: %s", type(exc).__name__)
        _discovery_error(
            "TOKEN_REFRESH_FAILED", "Salesforce token refresh failed", exc
        )

    try:
        update = persist_salesforce_token_refresh(datastore, connection_row, token_data)
    except (TypeError, ValueError, KeyError) as exc:
        logger.warning(
            "Salesforce token refresh rejected: errorCode=%s",
            token_data.get("error") if isinstance(token_data, dict) else "",
        )
        _discovery_error(
            "TOKEN_REFRESH_FAILED", "Salesforce token refresh failed", exc
        )
    return update["access_token"], update["instance_url"]


def _authorized_get(url, access_token, params=None, timeout=20):
    response = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
        params=params,
        timeout=timeout,
    )
    if not response.ok:
        logger.warning(
            "Salesforce metadata request failed: %s",
            _salesforce_error_summary(response),
        )
        response.raise_for_status()
    return response.json()


def normalize_salesforce_organization(record: dict, connection_row: dict) -> dict:
    """Map Organization sObject fields onto the metadata organization shape."""
    stored_id = str(connection_row.get("salesforce_org_id") or "").strip()
    stored_name = str(connection_row.get("organization_name") or "").strip()
    source = record if isinstance(record, dict) else {}
    organization_id = str(source.get("Id") or stored_id).strip()
    organization_name = str(source.get("Name") or "").strip() or stored_name
    time_zone = str(source.get("TimeZoneSidKey") or "").strip()
    organization_type = str(source.get("OrganizationType") or "").strip()
    if "IsSandbox" in source:
        is_sandbox = source.get("IsSandbox") is True
    else:
        is_sandbox = None
    return {
        "id": organization_id,
        "name": organization_name,
        "timeZone": time_zone,
        "isSandbox": is_sandbox,
        "organizationType": organization_type,
    }


def persist_salesforce_organization_name(datastore, connection_row: dict, organization: dict):
    """Store Organization.Name on the existing organization_name column."""
    name = str((organization or {}).get("name") or "").strip()
    row_id = connection_row.get("ROWID")
    if not name or not row_id:
        return
    if name == str(connection_row.get("organization_name") or "").strip():
        return
    update = {"ROWID": row_id, "organization_name": name}
    datastore.table(SALESFORCE_CONNECTIONS_TABLE).update_row(update)
    connection_row.update(update)


def fetch_salesforce_organization(access_token: str, instance_url: str, connection_row: dict):
    """Read Organization Id/Name/timezone from the Organization sObject."""
    stored_id = str(connection_row.get("salesforce_org_id") or "").strip()
    try:
        payload = _authorized_get(
            f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/query",
            access_token,
            params={"q": SALESFORCE_ORGANIZATION_QUERY},
            timeout=15,
        )
        records = payload.get("records") or []
        record = records[0] if records else {}
        organization = normalize_salesforce_organization(record, connection_row)
        if not organization["id"]:
            _discovery_error(
                "ORGANIZATION_DISCOVERY_FAILED",
                "Could not read Salesforce organization metadata",
            )
        return organization
    except (requests.RequestException, ValueError, TypeError, IndexError) as exc:
        if stored_id:
            logger.warning(
                "Salesforce Organization query failed; using stored organization id"
            )
            return normalize_salesforce_organization({}, connection_row)
        _discovery_error(
            "ORGANIZATION_DISCOVERY_FAILED",
            "Could not read Salesforce organization metadata",
            exc,
        )


def _excluded_by_name(api_name: str) -> bool:
    if api_name in _EXCLUDED_STANDARD_OBJECTS:
        return True
    return any(api_name.endswith(suffix) for suffix in _EXCLUDED_NAME_SUFFIXES)


def is_crm_scan_object(sobject: dict) -> bool:
    """Keep queryable CRM records; drop setup, associated, and virtual objects."""
    api_name = str(sobject.get("name") or "").strip()
    if not api_name or _excluded_by_name(api_name):
        return False
    if sobject.get("queryable") is not True or sobject.get("retrieveable") is not True:
        return False
    if sobject.get("customSetting") is True or sobject.get("deprecatedAndHidden") is True:
        return False
    if not str(sobject.get("keyPrefix") or "").strip():
        return False
    if sobject.get("layoutable") is not True and sobject.get("custom") is not True:
        return False
    return True


def fetch_accessible_sobjects(access_token: str, instance_url: str) -> list:
    try:
        payload = _authorized_get(
            f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/sobjects",
            access_token,
            timeout=30,
        )
        sobjects = payload.get("sobjects") or []
    except (requests.RequestException, ValueError, TypeError) as exc:
        _discovery_error(
            "OBJECT_DISCOVERY_FAILED",
            "Could not read Salesforce object metadata",
            exc,
        )

    objects = []
    for sobject in sobjects:
        if not isinstance(sobject, dict) or not is_crm_scan_object(sobject):
            continue
        api_name = str(sobject.get("name") or "").strip()
        label = str(sobject.get("label") or api_name).strip() or api_name
        objects.append({"apiName": api_name, "label": label})
    objects.sort(key=lambda item: (item["label"].lower(), item["apiName"]))
    return objects
