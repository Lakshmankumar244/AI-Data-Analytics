"""Resolve where a Bulk Read extract lives: Stratus, legacy File Store, or nowhere.

New extracts persist `source_file_key` (Stratus object key). Legacy extracts
keep a numeric File Store id in `source_file_id`. Stratus is preferred whenever
a key is present. Do not treat `source_file_key` as numeric.
"""

from __future__ import annotations

from collections import namedtuple


BACKEND_STRATUS = "stratus"
BACKEND_FILESTORE = "filestore"

ExtractLocator = namedtuple("ExtractLocator", ("backend", "locator"))


def stratus_object_key(value):
    """Return a non-empty Stratus object key, or None.

    Presence is the only check. Keys are not numeric File Store ids, so this
    must not use str.isdigit().
    """
    key = str(value or "").strip()
    return key or None


def legacy_file_store_id(value):
    """Return a legacy numeric File Store id, or None."""
    file_id = str(value or "").strip()
    return file_id if file_id.isdigit() else None


def resolve_extract_locator(bulk_row):
    """Return the extract locator, preferring Stratus over legacy File Store."""
    row = bulk_row or {}
    key = stratus_object_key(row.get("source_file_key"))
    if key:
        return ExtractLocator(BACKEND_STRATUS, key)
    file_id = legacy_file_store_id(row.get("source_file_id"))
    if file_id:
        return ExtractLocator(BACKEND_FILESTORE, file_id)
    return None


def has_extract_locator(bulk_row):
    """True when either a Stratus key or a legacy numeric File Store id exists."""
    return resolve_extract_locator(bulk_row) is not None
