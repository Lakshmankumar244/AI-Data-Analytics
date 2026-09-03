"""Shared HTTP task-scheduling helpers."""

import hashlib
import json
from datetime import datetime, timezone

from flask import make_response
from common.core import get_current_user_id

def json_response(payload, status=200):
    return make_response(
        json.dumps(payload), status, {"Content-Type": "application/json"}
    )


def foreign_row_id(value):
    if isinstance(value, dict):
        return value.get("ROWID") or value.get("rowid")
    return value


def canonical_hash(value):
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def catalyst_datetime_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def job_identifier(job_response):
    if not isinstance(job_response, dict):
        return None
    for key in ("id", "job_id", "jobId", "JOBID"):
        value = job_response.get(key)
        if value is not None:
            return str(value)
    return None


def catalyst_error_details(exc):
    """Return safe Catalyst error diagnostics without request credentials."""
    details = {
        "type": type(exc).__name__,
        "message": str(exc)[:1000],
    }
    for attribute in ("code", "status_code"):
        value = getattr(exc, attribute, None)
        if value is not None:
            details[attribute] = value
    return details
