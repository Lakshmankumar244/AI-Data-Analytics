"""Compatibility exports for pipeline task routes."""

from pipeline.prepare_route import enqueue_prepare_batches
from pipeline.process_route import enqueue_process_batches

__all__ = ["enqueue_prepare_batches", "enqueue_process_batches"]
