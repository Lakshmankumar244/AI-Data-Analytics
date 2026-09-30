"""Provider-neutral Catalyst Data Store helpers for Job Functions."""

import hashlib
import json
from datetime import datetime, timezone


def foreign_row_id(value):
    if isinstance(value, dict):
        return value.get("ROWID") or value.get("rowid")
    return value


def numeric_row_id(value, label):
    row_id = str(foreign_row_id(value))
    if not row_id.isdigit():
        raise ValueError(f"{label} is invalid")
    return row_id


def canonical_json(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )


def canonical_hash(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def catalyst_datetime(value):
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def catalyst_datetime_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def query_one(zcql, query, table_name):
    results = zcql.execute_query(query)
    return results[0][table_name] if results else None


def query_all_rows(zcql, query_prefix, table_name, page_size=300):
    rows = []
    offset = 0
    while True:
        results = zcql.execute_query(
            f"{query_prefix} limit {offset},{page_size}"
        )
        page = [item[table_name] for item in results]
        rows.extend(page)
        if len(page) < page_size:
            return rows
        offset += page_size


def insert_rows_in_chunks(table, rows, chunk_size=100):
    for start in range(0, len(rows), chunk_size):
        table.insert_rows(rows[start : start + chunk_size])


def delete_rows_in_chunks(table, row_ids, chunk_size=200):
    ids = [int(row_id) for row_id in row_ids]
    for start in range(0, len(ids), chunk_size):
        table.delete_rows(ids[start : start + chunk_size])
