"""Route requests without changing public API paths."""

import zcatalyst_sdk
from flask import Request, make_response

from analytics.routes import get_scan_results, get_scan_status
from analytics.records import get_record_findings
from analytics.fixes import get_fix_plan
from analytics.trends import get_scan_trend
from bulk_read.download import download_bulk_read_result
from bulk_read.prepare import prepare_bulk_read
from bulk_read.status import refresh_bulk_read_status
from bulk_read.submit import submit_bulk_read_job
from common.core import json_response
from connections.routes import activate_connection, get_connection, handle_callback, start_consent
from orchestration.routes import advance_scan
from pipeline.task_routes import enqueue_prepare_batches, enqueue_process_batches
from scans.routes import create_scan, discover_scan
from scans.history import list_scans
from scans.delete import delete_scan

def dispatch(request: Request):
    app = zcatalyst_sdk.initialize()
    datastore = app.datastore()

    if request.path == "/api/zoho/consent":
        return start_consent(request, datastore)

    if request.path == "/api/zoho/callback":
        return handle_callback(request, datastore)

    if request.path == "/api/zoho/connection":
        return get_connection(request, datastore)

    path_parts = request.path.strip("/").split("/")
    if (
        len(path_parts) == 5
        and path_parts[:3] == ["api", "zoho", "connections"]
        and path_parts[4] == "activate"
    ):
        if request.method != "POST":
            response = json_response(
                {"error": {"code": "METHOD_NOT_ALLOWED", "message": "Use POST"}},
                405,
            )
            response.headers["Allow"] = "POST"
            return response
        return activate_connection(request, datastore, path_parts[3])

    if request.path == "/api/scans":
        if request.method == "GET":
            return list_scans(request, datastore)
        if request.method != "POST":
            response = json_response(
                {"error": {"code": "METHOD_NOT_ALLOWED", "message": "Use GET or POST"}},
                405,
            )
            response.headers["Allow"] = "GET, POST"
            return response
        return create_scan(request, datastore)

    if len(path_parts) == 3 and path_parts[:2] == ["api", "scans"]:
        if request.method != "DELETE":
            response = json_response(
                {"error": {"code": "METHOD_NOT_ALLOWED", "message": "Use DELETE"}},
                405,
            )
            response.headers["Allow"] = "DELETE"
            return response
        return delete_scan(request, datastore, path_parts[2])

    if (
        len(path_parts) == 4
        and path_parts[:2] == ["api", "scans"]
        and path_parts[3] in {"status", "results", "trend", "records", "fix-plan"}
    ):
        if request.method != "GET":
            response = json_response(
                {"error": {"code": "METHOD_NOT_ALLOWED", "message": "Use GET"}},
                405,
            )
            response.headers["Allow"] = "GET"
            return response
        if path_parts[3] == "status":
            return get_scan_status(request, datastore, path_parts[2])
        if path_parts[3] == "trend":
            return get_scan_trend(request, datastore, path_parts[2])
        if path_parts[3] == "records":
            return get_record_findings(request, datastore, path_parts[2])
        if path_parts[3] == "fix-plan":
            return get_fix_plan(request, datastore, path_parts[2])
        return get_scan_results(request, datastore, path_parts[2])

    if len(path_parts) == 4 and path_parts[:2] == ["api", "scans"] and path_parts[3] == "discover":
        if request.method != "POST":
            response = json_response(
                {"error": {"code": "METHOD_NOT_ALLOWED", "message": "Use POST"}},
                405,
            )
            response.headers["Allow"] = "POST"
            return response
        return discover_scan(request, datastore, path_parts[2])

    if len(path_parts) == 4 and path_parts[:2] == ["api", "scans"] and path_parts[3] == "advance":
        if request.method != "POST":
            response = json_response(
                {"error": {"code": "METHOD_NOT_ALLOWED", "message": "Use POST"}},
                405,
            )
            response.headers["Allow"] = "POST"
            return response
        return advance_scan(request, datastore, path_parts[2])

    if len(path_parts) == 4 and path_parts[:2] == ["api", "scans"] and path_parts[3] == "prepare-bulk":
        if request.method != "POST":
            response = json_response(
                {"error": {"code": "METHOD_NOT_ALLOWED", "message": "Use POST"}},
                405,
            )
            response.headers["Allow"] = "POST"
            return response
        return prepare_bulk_read(request, datastore, path_parts[2])

    if (
        len(path_parts) == 6
        and path_parts[:2] == ["api", "scans"]
        and path_parts[3] == "bulk-jobs"
        and path_parts[5] == "submit"
    ):
        if request.method != "POST":
            response = json_response(
                {"error": {"code": "METHOD_NOT_ALLOWED", "message": "Use POST"}},
                405,
            )
            response.headers["Allow"] = "POST"
            return response
        return submit_bulk_read_job(
            request, datastore, path_parts[2], path_parts[4]
        )

    if (
        len(path_parts) == 6
        and path_parts[:2] == ["api", "scans"]
        and path_parts[3] == "bulk-jobs"
        and path_parts[5] == "refresh-status"
    ):
        if request.method != "POST":
            response = json_response(
                {"error": {"code": "METHOD_NOT_ALLOWED", "message": "Use POST"}},
                405,
            )
            response.headers["Allow"] = "POST"
            return response
        return refresh_bulk_read_status(
            request, datastore, path_parts[2], path_parts[4]
        )

    if (
        len(path_parts) == 6
        and path_parts[:2] == ["api", "scans"]
        and path_parts[3] == "bulk-jobs"
        and path_parts[5] == "download"
    ):
        if request.method != "POST":
            response = json_response(
                {"error": {"code": "METHOD_NOT_ALLOWED", "message": "Use POST"}},
                405,
            )
            response.headers["Allow"] = "POST"
            return response
        return download_bulk_read_result(
            request, datastore, path_parts[2], path_parts[4]
        )

    if (
        len(path_parts) == 6
        and path_parts[:2] == ["api", "scans"]
        and path_parts[3] == "bulk-jobs"
        and path_parts[5] == "prepare-processing"
    ):
        if request.method != "POST":
            response = json_response(
                {"error": {"code": "METHOD_NOT_ALLOWED", "message": "Use POST"}},
                405,
            )
            response.headers["Allow"] = "POST"
            return response
        return enqueue_prepare_batches(
            request, datastore, path_parts[2], path_parts[4]
        )

    if (
        len(path_parts) == 6
        and path_parts[:2] == ["api", "scans"]
        and path_parts[3] == "bulk-jobs"
        and path_parts[5] == "process-batches"
    ):
        if request.method != "POST":
            response = json_response(
                {"error": {"code": "METHOD_NOT_ALLOWED", "message": "Use POST"}},
                405,
            )
            response.headers["Allow"] = "POST"
            return response
        return enqueue_process_batches(
            request, datastore, path_parts[2], path_parts[4]
        )

    return make_response("Not found", 404)
