"""Shared durable Job Function task-state helpers."""

from datetime import timezone


def catalyst_datetime(value):
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def query_one(zcql, query, table_name):
    results = zcql.execute_query(query)
    return results[0][table_name] if results else None
