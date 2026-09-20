"""Build deterministic Zoho Bulk Read request bodies."""

import json

from common.core import SCAN_CLOCK_FIELDS, to_zoho_datetime

def build_bulk_read_request(scan_row: dict, module_row: dict) -> dict:
    try:
        fields = json.loads(module_row.get("field_allowlist_json") or "[]")
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("The stored field allowlist is invalid") from exc
    if not isinstance(fields, list) or not fields or not all(
        isinstance(field, str) and field for field in fields
    ):
        raise ValueError("The stored field allowlist is invalid")

    clock_field = scan_row.get("clock_field")
    to_utc = scan_row.get("to_utc")
    if clock_field not in SCAN_CLOCK_FIELDS.values() or not to_utc:
        raise ValueError("The stored scan window is invalid")

    upper_bound = {
        "field": {"api_name": clock_field},
        "comparator": "less_than",
        "value": to_zoho_datetime(to_utc),
    }
    from_utc = scan_row.get("from_utc")
    if from_utc:
        criteria = {
            "group": [
                {
                    "field": {"api_name": clock_field},
                    "comparator": "greater_equal",
                    "value": to_zoho_datetime(from_utc),
                },
                upper_bound,
            ],
            "group_operator": "and",
        }
    else:
        criteria = upper_bound

    return {
        "query": {
            "module": {"api_name": module_row["module_api_name"]},
            "fields": fields,
            "criteria": criteria,
            "page": 1,
        }
    }
