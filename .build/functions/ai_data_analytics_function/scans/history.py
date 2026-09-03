"""Authenticated scan-history API built from durable aggregate metadata."""

import logging

import zcatalyst_sdk

from common.core import AuthenticationRequired, get_current_user_id, json_response


LOGGER = logging.getLogger(__name__)


def _rows(zcql, query, table_name):
    return [item[table_name] for item in zcql.execute_query(query)]


def _integer(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def list_scans(request, datastore):
    """Return recent scans belonging only to the current Catalyst user."""
    del datastore
    try:
        zcql = zcatalyst_sdk.initialize().zcql()
        user_id = get_current_user_id(request).replace("'", "''")
        connections = _rows(
            zcql,
            f"select * from zoho_connections where user_id = '{user_id}'",
            "zoho_connections",
        )
        scans = []
        for connection in connections:
            connection_row_id = int(connection["ROWID"])
            connection_scans = _rows(
                zcql,
                "select * from scan_jobs where "
                f"connection_row_id = {connection_row_id} "
                "order by CREATEDTIME desc limit 50",
                "scan_jobs",
            )
            for scan in connection_scans:
                scan["_source_connection"] = {
                    "connectionId": str(connection["ROWID"]),
                    "organizationId": str(connection.get("zoho_org_id") or ""),
                    "organizationName": str(
                        connection.get("organization_name") or ""
                    ),
                    "name": str(connection.get("connected_name") or ""),
                    "email": str(connection.get("connected_email") or ""),
                    "isActive": connection.get("is_active") is True
                    or str(connection.get("is_active") or "").lower() == "true",
                }
                scans.append(scan)

        history = []
        for scan in scans:
            scan_row_id = int(scan["ROWID"])
            modules = _rows(
                zcql,
                "select * from scan_module_runs where "
                f"scan_row_id = {scan_row_id}",
                "scan_module_runs",
            )
            results = _rows(
                zcql,
                "select metric_group,status,source_record_count from analytics_results where "
                f"scan_row_id = {scan_row_id}",
                "analytics_results",
            )
            summary_results = [
                row
                for row in results
                if row.get("status") == "COMPUTED"
                and row.get("metric_group") == "summary"
            ]
            record_count = sum(
                _integer(row.get("source_record_count")) for row in summary_results
            )
            history.append(
                {
                    "scanId": scan.get("scan_id"),
                    "status": scan.get("status"),
                    "modules": sorted(
                        str(module.get("module_api_name"))
                        for module in modules
                        if module.get("module_api_name")
                    ),
                    "clock": scan.get("clock_field"),
                    "fromUtc": str(scan.get("from_utc") or ""),
                    "toUtc": str(scan.get("to_utc") or ""),
                    "depth": scan.get("depth_policy"),
                    "recordCount": record_count,
                    "createdAt": str(scan.get("CREATEDTIME") or ""),
                    "completedAt": str(scan.get("completed_at") or ""),
                    "hasResults": bool(summary_results),
                    "connection": scan["_source_connection"],
                }
            )

        history.sort(
            key=lambda item: (item["createdAt"], item["scanId"] or ""),
            reverse=True,
        )
        return json_response({"scans": history[:50]})
    except AuthenticationRequired:
        raise
    except Exception as exc:  # noqa: BLE001 - keep storage diagnostics server-side
        LOGGER.exception("Could not list scan history: %s", exc)
        return json_response(
            {
                "error": {
                    "code": "SCAN_HISTORY_READ_FAILED",
                    "message": "Scan history could not be read",
                }
            },
            500,
        )
