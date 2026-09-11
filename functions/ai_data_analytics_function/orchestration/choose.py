"""Choose the next deterministic scan-pipeline action without changing state."""

from common.core import foreign_row_id


ACTIVE_TASK_STATES = {"QUEUED", "RUNNING"}
ORCHESTRATE_TASK_TYPE = "ORCHESTRATE_SCAN"
ACTIVE_ORCHESTRATE_STATES = {"PLANNED", "QUEUED", "RUNNING"}


def latest_task(state, bulk_row, task_type):
    matches = [
        task
        for task in state["tasks"]
        if str(foreign_row_id(task.get("bulk_job_row_id"))) == str(bulk_row["ROWID"])
        and task.get("task_type") == task_type
    ]
    return max(matches, key=lambda row: int(row.get("ROWID") or 0), default=None)


def latest_orchestrate_task(state):
    matches = [
        task
        for task in state["tasks"]
        if task.get("task_type") == ORCHESTRATE_TASK_TYPE
    ]
    return max(matches, key=lambda row: int(row.get("ROWID") or 0), default=None)


def orchestrate_owns_scan(state):
    task = latest_orchestrate_task(state)
    if not task:
        return False, None
    return str(task.get("status") or "") in ACTIVE_ORCHESTRATE_STATES, task


def choose_action(state):
    """Return the next deterministic action without changing any state."""
    scan_status = str(state["scan"].get("status") or "")
    if scan_status == "COMPLETED":
        return {"name": "COMPLETE", "next": None}
    if scan_status == "FAILED_TERMINAL":
        return {"name": "BLOCKED", "next": "REVIEW_FAILURE"}
    if scan_status in {"CREATED", "DISCOVERING", "PAUSED_RETRYABLE"}:
        return {"name": "DISCOVER", "next": "PREPARE_BULK"}

    modules = sorted(
        state["modules"], key=lambda row: int(row.get("ROWID") or 0)
    )
    if not modules:
        return {"name": "BLOCKED", "next": "REVIEW_SCAN_PLAN"}

    all_jobs = [
        job
        for module in modules
        for job in state["bulk_jobs_by_module"].get(str(module["ROWID"]), [])
    ]
    if not all_jobs:
        return {"name": "PREPARE_BULK", "next": "SUBMIT_BULK"}

    for module in modules:
        jobs = sorted(
            state["bulk_jobs_by_module"].get(str(module["ROWID"]), []),
            key=lambda row: (
                int(row.get("provider_page") or 0),
                str(row.get("bulk_job_id") or ""),
            ),
        )
        if not jobs:
            return {"name": "BLOCKED", "next": "REVIEW_BULK_PLAN"}
        for bulk in jobs:
            status = str(bulk.get("status") or "")
            target = {"bulk": bulk, "module": module}
            if status == "PLANNED":
                return {
                    "name": "SUBMIT_BULK",
                    "next": "CHECK_BULK_STATUS",
                    **target,
                }
            if status == "SUBMITTED" or (
                status == "PROCESSING" and not bulk.get("source_file_id")
            ):
                return {
                    "name": "CHECK_BULK_STATUS",
                    "next": "CHECK_BULK_STATUS",
                    **target,
                }
            if status in {"READY_TO_DOWNLOAD", "DOWNLOAD_RETRYABLE"}:
                return {
                    "name": "DOWNLOAD_RESULT",
                    "next": "PREPARE_BATCHES",
                    **target,
                }
            if status == "DOWNLOADED":
                task = latest_task(state, bulk, "PREPARE_BATCHES")
                if task and task.get("status") in ACTIVE_TASK_STATES:
                    return {
                        "name": "WAIT_FOR_WORKER",
                        "next": "PREPARE_BATCHES",
                        "task": task,
                        **target,
                    }
                if task and task.get("status") == "OUTCOME_UNKNOWN":
                    return {
                        "name": "BLOCKED",
                        "next": "REVIEW_WORKER_JOB",
                        "task": task,
                        **target,
                    }
                return {
                    "name": "PREPARE_BATCHES",
                    "next": "PROCESS_BATCHES",
                    **target,
                }
            if status in {"PROCESSING_PLANNED", "PROCESSING"} and bulk.get(
                "source_file_id"
            ):
                task = latest_task(state, bulk, "PROCESS_BATCHES")
                if task and task.get("status") in ACTIVE_TASK_STATES:
                    return {
                        "name": "WAIT_FOR_WORKER",
                        "next": "PROCESS_BATCHES",
                        "task": task,
                        **target,
                    }
                if task and task.get("status") == "OUTCOME_UNKNOWN":
                    return {
                        "name": "BLOCKED",
                        "next": "REVIEW_WORKER_JOB",
                        "task": task,
                        **target,
                    }
                return {
                    "name": "PROCESS_BATCHES",
                    "next": "WAIT_FOR_WORKER",
                    **target,
                }
            if status == "PROCESSED":
                continue
            return {"name": "BLOCKED", "next": "REVIEW_BULK_JOB", **target}

    return {"name": "WAIT_FOR_COMPLETION", "next": "REFRESH_STATUS"}
