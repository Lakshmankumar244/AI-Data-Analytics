"""Read-only Zoho CRM metadata and module-count operations."""

import logging
import os
from concurrent.futures import ThreadPoolExecutor

import requests

from common.core import BASE_FIELD_ALLOWLIST, QUALITY_FIELD_CANDIDATES, DiscoveryError

logger = logging.getLogger(__name__)

def fetch_organization_metadata(access_token: str, api_domain: str) -> dict:
    try:
        response = requests.get(
            f"{api_domain}/crm/v6/org",
            headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
            timeout=15,
        )
        response.raise_for_status()
        organizations = response.json().get("org", [])
    except (requests.RequestException, ValueError) as exc:
        raise DiscoveryError(
            "ORGANIZATION_DISCOVERY_FAILED", "Could not read Zoho organization metadata"
        ) from exc
    if not organizations or not organizations[0].get("time_zone"):
        raise DiscoveryError(
            "ORGANIZATION_TIMEZONE_MISSING", "Zoho organization timezone is unavailable"
        )
    return organizations[0]


def fetch_module_fields(access_token: str, api_domain: str, module_api_name: str) -> list:
    try:
        response = requests.get(
            f"{api_domain}/crm/v6/settings/fields",
            params={"module": module_api_name},
            headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
            timeout=20,
        )
        response.raise_for_status()
        return response.json().get("fields", [])
    except (requests.RequestException, ValueError) as exc:
        raise DiscoveryError(
            "FIELD_DISCOVERY_FAILED",
            f"Could not read field metadata for {module_api_name}",
        ) from exc


def build_field_allowlist(fields: list) -> list:
    selected = set(BASE_FIELD_ALLOWLIST)
    for field in fields:
        api_name = field.get("api_name")
        if not api_name or field.get("virtual_field"):
            continue
        private_config = field.get("private") or {}
        if private_config.get("restricted"):
            continue
        if (
            api_name in QUALITY_FIELD_CANDIDATES
            or field.get("system_mandatory")
            or bool(field.get("unique"))
        ):
            selected.add(api_name)
    return [*BASE_FIELD_ALLOWLIST, *sorted(selected - set(BASE_FIELD_ALLOWLIST))]


def build_field_metadata(fields: list, allowlist: list) -> list:
    """Retain only field properties needed for deterministic finding rules."""
    fields_by_name = {
        str(field.get("api_name")): field
        for field in fields
        if field.get("api_name")
    }
    metadata = []
    for api_name in allowlist:
        field = fields_by_name.get(api_name, {})
        metadata.append(
            {
                "apiName": api_name,
                "label": str(
                    field.get("field_label")
                    or field.get("display_label")
                    or api_name
                )[:100],
                "dataType": str(field.get("data_type") or "")[:40],
                "systemMandatory": bool(field.get("system_mandatory")),
                "unique": bool(field.get("unique")),
                "readOnly": bool(field.get("read_only")),
                "custom": bool(field.get("custom_field")),
            }
        )
    return metadata


def fetch_record_count(
    access_token: str,
    api_domain: str,
    module_api_name: str,
    criteria: str = None,
) -> int:
    params = {"criteria": criteria} if criteria else None
    resp = requests.get(
        f"{api_domain}/crm/v6/{module_api_name}/actions/count",
        params=params,
        headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("count", 0)


def refresh_module_record_counts(
    access_token: str,
    api_domain: str,
    modules: list,
) -> list:
    """Replace stored recordCount values with live Zoho CRM totals."""
    candidates = [
        dict(module)
        for module in modules
        if isinstance(module, dict) and module.get("apiName")
    ]

    def with_count(mod):
        try:
            mod["recordCount"] = fetch_record_count(
                access_token, api_domain, mod["apiName"]
            )
        except requests.RequestException as exc:
            logger.warning(
                "Could not refresh record count for %s: %s", mod["apiName"], exc
            )
            try:
                mod["recordCount"] = int(mod.get("recordCount") or 0)
            except (TypeError, ValueError):
                mod["recordCount"] = 0
        return mod

    if not candidates:
        return []
    with ThreadPoolExecutor(max_workers=5) as pool:
        return list(pool.map(with_count, candidates))


def build_count_criteria(conditions: list) -> str:
    """Build Zoho Search/count criteria from trusted field/operator/value tuples."""
    expressions = [
        f"{field}:{operator}:{value}"
        for field, operator, value in conditions
    ]
    if len(expressions) == 1:
        return expressions[0]
    return "(" + "and".join(f"({expression})" for expression in expressions) + ")"


def has_modified_records_since(
    access_token: str,
    api_domain: str,
    module_api_name: str,
    modified_since: str,
) -> bool:
    """Use Zoho's conditional record read as a low-payload change probe."""
    response = requests.get(
        f"{api_domain}/crm/v6/{module_api_name}",
        params={
            "fields": "Modified_Time",
            "per_page": 1,
            "sort_by": "Modified_Time",
            "sort_order": "desc",
        },
        headers={
            "Authorization": f"Zoho-oauthtoken {access_token}",
            "If-Modified-Since": modified_since,
        },
        timeout=15,
    )
    if response.status_code in {204, 304}:
        return False
    response.raise_for_status()
    return bool(response.json().get("data"))


RECORD_NAME_FIELDS = (
    "Deal_Name",
    "Account_Name",
    "Full_Name",
    "First_Name",
    "Last_Name",
    "Company",
    "Name",
)
MODULE_NAME_FIELDS = {
    "Deals": ("Deal_Name",),
    "Accounts": ("Account_Name",),
    "Leads": ("Full_Name", "First_Name", "Last_Name", "Company"),
    "Contacts": ("Full_Name", "First_Name", "Last_Name"),
}


def _crm_display_name(record: dict) -> str:
    for field_name in ("Deal_Name", "Account_Name", "Full_Name"):
        value = str(record.get(field_name) or "").strip()
        if value:
            return value
    person = " ".join(
        part
        for part in (
            str(record.get("First_Name") or "").strip(),
            str(record.get("Last_Name") or "").strip(),
        )
        if part
    )
    if person:
        return person
    for field_name in ("Company", "Name"):
        value = str(record.get(field_name) or "").strip()
        if value:
            return value
    return ""


def fetch_record_names(
    access_token: str,
    api_domain: str,
    module_api_name: str,
    record_ids: list,
) -> dict:
    """Resolve Deal / Account / Lead names for stored CRM record ids."""
    ids = []
    seen = set()
    for record_id in record_ids:
        candidate = str(record_id or "").strip()
        if candidate.isdigit() and candidate not in seen:
            seen.add(candidate)
            ids.append(candidate)
    if not ids or not module_api_name:
        return {}

    field_sets = [
        MODULE_NAME_FIELDS.get(module_api_name, ("Name",)),
        ("Name",),
        RECORD_NAME_FIELDS,
    ]
    names = {}
    for start in range(0, len(ids), 100):
        chunk = ids[start : start + 100]
        records = []
        for fields in field_sets:
            try:
                response = requests.get(
                    f"{api_domain}/crm/v6/{module_api_name}",
                    params={
                        "ids": ",".join(chunk),
                        "fields": ",".join(fields),
                        "per_page": min(len(chunk), 100),
                    },
                    headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
                    timeout=20,
                )
                response.raise_for_status()
                records = response.json().get("data") or []
                break
            except (requests.RequestException, ValueError, TypeError) as exc:
                logger.warning(
                    "Could not read %s record names with fields %s: %s",
                    module_api_name,
                    ",".join(fields),
                    exc,
                )
        for record in records:
            record_id = str(record.get("id") or "").strip()
            name = _crm_display_name(record)
            if record_id and name:
                names[record_id] = name
    return names


def fetch_accessible_modules(access_token: str, api_domain: str = None) -> list:
    api_domain = api_domain or os.environ["ZOHO_API_DOMAIN"]
    resp = requests.get(
        f"{api_domain}/crm/v6/settings/modules",
        headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
        timeout=15,
    )
    resp.raise_for_status()

    candidates = [
        {"apiName": m["api_name"], "label": m.get("plural_label", m["api_name"])}
        for m in resp.json().get("modules", [])
        if m.get("api_supported") and m.get("visible", True)
    ]

    def with_count(mod):
        try:
            mod["recordCount"] = fetch_record_count(access_token, api_domain, mod["apiName"])
        except requests.RequestException as exc:
            # Don't let one module's count call take down the whole
            # connection attempt - default to 0 and keep going.
            logger.warning("Could not fetch record count for %s: %s", mod["apiName"], exc)
            mod["recordCount"] = 0
        return mod

    # Concurrent, not unlimited - capped so this doesn't hammer Zoho's rate
    # limit. 5 is a reasonable starting point, not a number I've verified
    # against Zoho's documented limit for your account tier - tune down if
    # you start seeing 429s.
    with ThreadPoolExecutor(max_workers=5) as pool:
        modules = list(pool.map(with_count, candidates))

    return modules
