"""Dispatch a durable pipeline task to its bounded worker stage."""

from pipeline.processing import process_and_finalize
from tasks.prepare_batches import prepare_batches
from worker.continue_process import continue_to_process_batches
from worker.orchestrate import orchestrate_scan


def dispatch_task(app, task_row):
    task_type = task_row.get("task_type")
    if task_type == "ORCHESTRATE_SCAN":
        return orchestrate_scan(app, task_row)
    if task_type == "PREPARE_BATCHES":
        prepare_result = prepare_batches(app, task_row)
        process_result = continue_to_process_batches(app, task_row)
        if isinstance(prepare_result, dict):
            return {**prepare_result, "processBatches": process_result}
        return {"prepare": prepare_result, "processBatches": process_result}
    if task_type == "PROCESS_BATCHES":
        return process_and_finalize(app, task_row)
    raise ValueError(f"Unsupported task type {task_type}")
