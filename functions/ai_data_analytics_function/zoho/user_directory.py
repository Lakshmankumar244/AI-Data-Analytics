"""Cache the Zoho CRM user directory for owner-name resolution."""

import logging
from datetime import datetime, timedelta, timezone

import requests

from common.core import (
    canonical_hash,
    foreign_row_id,
    from_catalyst_datetime,
    to_catalyst_column_datetime,
)

logger = logging.getLogger(__name__)

DIRECTORY_TTL = timedelta(hours=24)
USERS_PER_PAGE = 200
MAX_USER_PAGES = 50


def _is_fresh(rows, now_utc):
    timestamps = []
    for row in rows:
        value = row.get("synced_at")
        if not value:
            continue
        try:
            timestamps.append(from_catalyst_datetime(str(value)))
        except ValueError:
            continue
    return bool(timestamps) and now_utc - max(timestamps) < DIRECTORY_TTL


def _fetch_users(access_token, api_domain):
    users = []
    api_calls = 0
    for page in range(1, MAX_USER_PAGES + 1):
        api_calls += 1
        try:
            response = requests.get(
                f"{api_domain}/crm/v6/users",
                params={"type": "AllUsers", "page": page, "per_page": USERS_PER_PAGE},
                headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            return None, api_calls, f"CRM user directory request failed: {type(exc).__name__}"

        if not isinstance(payload, dict):
            return None, api_calls, "CRM user directory response was invalid"
        page_users = payload.get("users", [])
        if not isinstance(page_users, list):
            return None, api_calls, "CRM user directory response was invalid"
        users.extend(page_users)
        if not bool((payload.get("info") or {}).get("more_records")):
            return users, api_calls, None

    return None, api_calls, "CRM user directory exceeded the supported page limit"


def sync_connection_user_directory(datastore, zcql, connection_row, access_token, api_domain):
    """Refresh a connection's directory when absent or older than 24 hours.

    Directory refresh is deliberately best-effort. A temporary Users API or
    Data Store failure must not prevent the scan's quality aggregation.
    """
    connection_row_id = str(foreign_row_id(connection_row.get("ROWID")) or "")
    if not connection_row_id.isdigit():
        return {
            "refreshed": False,
            "apiCalls": 0,
            "userCount": 0,
            "warning": "Connection identifier is invalid for directory caching",
        }

    try:
        results = zcql.execute_query(
            "select * from zoho_connection_users where "
            f"connection_row_id = {connection_row_id}"
        )
        existing_rows = [item["zoho_connection_users"] for item in results]
    except Exception as exc:  # noqa: BLE001 - cache failure is non-fatal
        logger.exception("Could not read CRM user directory cache: %s", exc)
        return {
            "refreshed": False,
            "apiCalls": 0,
            "userCount": 0,
            "warning": "CRM user directory cache could not be read",
        }

    now_utc = datetime.now(timezone.utc)
    if _is_fresh(existing_rows, now_utc):
        return {
            "refreshed": False,
            "apiCalls": 0,
            "userCount": sum(
                1 for row in existing_rows if str(row.get("status") or "").upper() == "ACTIVE"
            ),
            "warning": None,
        }

    users, api_calls, warning = _fetch_users(access_token, api_domain)
    if users is None:
        logger.warning("CRM user directory was not refreshed: %s", warning)
        return {
            "refreshed": False,
            "apiCalls": api_calls,
            "userCount": 0,
            "warning": warning,
        }

    existing_by_key = {
        str(row.get("directory_key") or ""): row
        for row in existing_rows
        if row.get("directory_key")
    }
    seen_keys = set()
    synced_at = to_catalyst_column_datetime(now_utc)
    table = datastore.table("zoho_connection_users")
    try:
        for user in users:
            crm_user_id = str(user.get("id") or user.get("zuid") or "").strip()
            if not crm_user_id:
                continue
            crm_user_key = canonical_hash({"crm_user_id": crm_user_id})
            directory_key = canonical_hash(
                {
                    "connection_row_id": connection_row_id,
                    "crm_user_id": crm_user_id,
                }
            )
            display_name = str(
                user.get("full_name") or user.get("name") or "Unknown owner"
            ).strip()[:255]
            status = str(user.get("status") or "ACTIVE").strip().upper()[:40]
            row_data = {
                "directory_id": f"userdir_{directory_key[:32]}",
                "directory_key": directory_key,
                "connection_row_id": connection_row_id,
                "crm_user_key": crm_user_key,
                "crm_user_id": crm_user_id,
                "display_name": display_name or "Unknown owner",
                "status": status or "ACTIVE",
                "synced_at": synced_at,
            }
            existing = existing_by_key.get(directory_key)
            if existing:
                row_data["ROWID"] = existing["ROWID"]
                table.update_row(row_data)
            else:
                table.insert_row(row_data)
            seen_keys.add(directory_key)

        for directory_key, row in existing_by_key.items():
            if directory_key not in seen_keys and str(row.get("status") or "").upper() != "INACTIVE":
                table.update_row(
                    {
                        "ROWID": row["ROWID"],
                        "status": "INACTIVE",
                        "synced_at": synced_at,
                    }
                )
    except Exception as exc:  # noqa: BLE001 - scan may continue with unknown owners
        logger.exception("Could not persist CRM user directory cache: %s", exc)
        return {
            "refreshed": False,
            "apiCalls": api_calls,
            "userCount": 0,
            "warning": "CRM user directory cache could not be stored",
        }

    return {
        "refreshed": True,
        "apiCalls": api_calls,
        "userCount": len(seen_keys),
        "warning": None,
    }
