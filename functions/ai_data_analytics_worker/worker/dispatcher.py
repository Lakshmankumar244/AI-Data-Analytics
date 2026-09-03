"""Dispatch a durable pipeline task to its bounded worker stage."""

from pipeline.processing import process_and_finalize
from tasks.prepare_batches import prepare_batches


def dispatch_task(app, task_row):
    task_type = task_row.get("task_type")
    if task_type == "PREPARE_BATCHES":
        return prepare_batches(app, task_row)
    if task_type == "PROCESS_BATCHES":
        return process_and_finalize(app, task_row)
    raise ValueError(f"Unsupported task type {task_type}")
