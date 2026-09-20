"""Claim a Salesforce pipeline task the same way the Zoho worker leases work.

Uses existing pipeline_tasks columns (status, attempt_count, started_at,
lease_expires_at). Does not create a Salesforce-specific task table.
"""

from datetime import datetime, timedelta, timezone

from task_resolve import SalesforceWorkerError


LEASE_MINUTES = 10
CLAIMABLE_TASK_STATES = frozenset(
    {"PLANNED", "QUEUED", "PAUSED_RETRYABLE", "OUTCOME_UNKNOWN"}
)
ALREADY_COMPLETE = "already_complete"
ALREADY_RUNNING = "already_running"
CLAIMED = "claimed"


def _catalyst_datetime(now=None):
    value = now or datetime.now(timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _parse_catalyst_datetime(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text = str(value or "").strip()
    if not text:
        raise ValueError("empty datetime")
    for date_format in (
        "%Y-%m-%d %H:%M:%S:%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
    ):
        try:
            return datetime.strptime(text, date_format).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def lease_is_valid(task_row, now=None):
    now = now or datetime.now(timezone.utc)
    raw = (task_row or {}).get("lease_expires_at")
    if not raw:
        return False
    try:
        expires = _parse_catalyst_datetime(raw)
    except (TypeError, ValueError):
        return False
    return expires > now


def claim_salesforce_task(datastore, task_row, now=None):
    """Lease the existing pipeline_tasks row. RUNNING means this worker owns it."""
    now = now or datetime.now(timezone.utc)
    status = str((task_row or {}).get("status") or "")
    if status == "SUCCEEDED":
        return ALREADY_COMPLETE
    if status == "RUNNING" and lease_is_valid(task_row, now=now):
        return ALREADY_RUNNING
    if status == "RUNNING" and not lease_is_valid(task_row, now=now):
        pass
    elif status not in CLAIMABLE_TASK_STATES:
        raise SalesforceWorkerError(
            "PIPELINE_TASK_STATE_CONFLICT",
            f"Pipeline task cannot run from state {status}",
        )

    attempt_count = int((task_row or {}).get("attempt_count") or 0) + 1
    update = {
        "ROWID": task_row["ROWID"],
        "status": "RUNNING",
        "attempt_count": attempt_count,
        "started_at": _catalyst_datetime(now),
        "lease_expires_at": _catalyst_datetime(now + timedelta(minutes=LEASE_MINUTES)),
        "controlled_error_code": "",
    }
    datastore.table("pipeline_tasks").update_row(update)
    task_row.update(update)
    return CLAIMED
