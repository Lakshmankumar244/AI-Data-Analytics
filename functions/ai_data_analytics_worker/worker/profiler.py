"""Temporary SCAN_PROFILE timing. Log-only; does not change scan results."""

import json
import logging
import time
from contextlib import contextmanager
from datetime import datetime, timezone


logger = logging.getLogger("scan_profile")


def _utc_now():
    return datetime.now(timezone.utc)


class ScanProfiler:
    def __init__(self, scope, **meta):
        self.scope = scope
        self.meta = {key: value for key, value in meta.items() if value is not None}
        self.wall_start = _utc_now()
        self.mono_start = time.perf_counter()
        self.stages = []
        self.counters = {}
        self.ms = {}

    def add(self, key, n=1):
        self.counters[key] = self.counters.get(key, 0) + n

    def add_ms(self, key, ms):
        self.ms[key] = self.ms.get(key, 0.0) + ms

    def snapshot_ms(self):
        return dict(self.ms)

    def delta_ms(self, before):
        keys = set(self.ms) | set(before)
        return {
            key: round(self.ms.get(key, 0.0) - before.get(key, 0.0), 3) for key in keys
        }

    @contextmanager
    def stage(self, name, **meta):
        started = _utc_now()
        t0 = time.perf_counter()
        records_before = self.counters.get("records_processed", 0)
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            records = self.counters.get("records_processed", 0) - records_before
            elapsed_s = elapsed_ms / 1000.0
            rps = records / elapsed_s if elapsed_s > 0 and records else None
            event = {
                "stage": name,
                "start": started.isoformat(),
                "end": _utc_now().isoformat(),
                "elapsedMs": round(elapsed_ms, 3),
                "records": records,
                "recordsPerSecond": None if rps is None else round(rps, 2),
                **meta,
            }
            self.stages.append(event)
            payload = {"scope": self.scope, **self.meta, **event}
            logger.info("SCAN_PROFILE %s", json.dumps(payload, default=str))

    @contextmanager
    def accum(self, name):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.add_ms(name, (time.perf_counter() - t0) * 1000.0)

    def wrap_zcql(self, zcql):
        return _TimedZcql(zcql, self)

    def wrap_datastore(self, datastore):
        return _TimedDatastore(datastore, self)

    def compact(self):
        elapsed_ms = (time.perf_counter() - self.mono_start) * 1000.0
        records = int(self.counters.get("records_processed") or 0)
        elapsed_s = elapsed_ms / 1000.0
        return {
            **self.meta,
            "scope": self.scope,
            "start": self.wall_start.isoformat(),
            "end": _utc_now().isoformat(),
            "elapsedMs": round(elapsed_ms, 3),
            "records": records,
            "recordsPerSecond": (
                round(records / elapsed_s, 2) if elapsed_s > 0 and records else None
            ),
            "stages": [
                {
                    "stage": event["stage"],
                    "start": event["start"],
                    "end": event["end"],
                    "elapsedMs": event["elapsedMs"],
                    "records": event["records"],
                    "recordsPerSecond": event["recordsPerSecond"],
                    **{
                        key: value
                        for key, value in event.items()
                        if key
                        not in {
                            "stage",
                            "start",
                            "end",
                            "elapsedMs",
                            "records",
                            "recordsPerSecond",
                        }
                    },
                }
                for event in self.stages
            ],
            "accumMs": {key: round(value, 3) for key, value in self.ms.items()},
            "counters": dict(self.counters),
        }

    def summary(self):
        payload = self.compact()
        logger.info("SCAN_PROFILE_SUMMARY %s", json.dumps(payload, default=str))
        return payload


class ProfiledApp:
    def __init__(self, app, profiler):
        self._app = app
        self._profiler = profiler

    def zcql(self):
        return self._profiler.wrap_zcql(self._app.zcql())

    def datastore(self):
        return self._profiler.wrap_datastore(self._app.datastore())

    def filestore(self):
        return self._app.filestore()

    def __getattr__(self, name):
        return getattr(self._app, name)


class _TimedZcql:
    def __init__(self, inner, profiler):
        self._inner = inner
        self._profiler = profiler

    def execute_query(self, *args, **kwargs):
        self._profiler.add("datastore_read_calls")
        t0 = time.perf_counter()
        try:
            return self._inner.execute_query(*args, **kwargs)
        finally:
            self._profiler.add_ms(
                "datastore_reads", (time.perf_counter() - t0) * 1000.0
            )

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _TimedDatastore:
    def __init__(self, inner, profiler):
        self._inner = inner
        self._profiler = profiler

    def table(self, name):
        return _TimedTable(self._inner.table(name), self._profiler)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _TimedTable:
    def __init__(self, inner, profiler):
        self._inner = inner
        self._profiler = profiler

    def _write(self, op, row_count, callback):
        self._profiler.add("datastore_write_calls")
        self._profiler.add("datastore_write_rows", row_count)
        t0 = time.perf_counter()
        try:
            return callback()
        finally:
            self._profiler.add_ms(
                "datastore_writes", (time.perf_counter() - t0) * 1000.0
            )

    def insert_row(self, *args, **kwargs):
        return self._write(
            "insert_row", 1, lambda: self._inner.insert_row(*args, **kwargs)
        )

    def insert_rows(self, rows, *args, **kwargs):
        return self._write(
            "insert_rows",
            len(rows),
            lambda: self._inner.insert_rows(rows, *args, **kwargs),
        )

    def update_row(self, *args, **kwargs):
        return self._write(
            "update_row", 1, lambda: self._inner.update_row(*args, **kwargs)
        )

    def __getattr__(self, name):
        return getattr(self._inner, name)
