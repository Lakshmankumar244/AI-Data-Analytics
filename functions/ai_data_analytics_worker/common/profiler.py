"""Temporary SCAN_PROFILE timing. Log-only; does not change API responses."""

import json
import logging
import time
from contextlib import contextmanager
from datetime import datetime, timezone


logger = logging.getLogger("scan_profile")


@contextmanager
def profile_stage(scope, name, **meta):
    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        payload = {
            "scope": scope,
            "stage": name,
            "start": started.isoformat(),
            "end": datetime.now(timezone.utc).isoformat(),
            "elapsedMs": round(elapsed_ms, 3),
            **{key: value for key, value in meta.items() if value is not None},
        }
        logger.info("SCAN_PROFILE %s", json.dumps(payload, default=str))
