"""Shared CRM extract storage: private Stratus with legacy File Store dual-read."""

from storage.locator import (
    BACKEND_FILESTORE,
    BACKEND_STRATUS,
    ExtractLocator,
    has_extract_locator,
    legacy_file_store_id,
    resolve_extract_locator,
    stratus_object_key,
)
