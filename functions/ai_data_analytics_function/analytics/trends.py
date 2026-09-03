"""Authenticated, aggregate-only quality trends across completed scans."""

import json
import logging
from datetime import datetime

import zcatalyst_sdk

from analytics.repository import find_analytics_results, find_owned_scan
from common.core import (
    AuthenticationRequired,
    foreign_row_id,
    get_current_user_id,
    json_response,
    query_list_values,
)


LOGGER = logging.getLogger(__name__)
MAX_TREND_POINTS = 12
DOMAIN_WEIGHTS = {
    "completeness": 20,
    "duplication": 20,
    "validity": 15,
    "plausibility": 10,
    "freshness": 10,
    "integrity": 10,
    "config": 8,
    "pii": 4,
    "automation": 3,
}


def _rows(zcql, query, table_name):
    return [item[table_name] for item in zcql.execute_query(query)]


def _integer(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _score(domain_scores):
    measured = [
        (value, DOMAIN_WEIGHTS[domain])
        for domain, value in domain_scores.items()
        if value is not None and domain in DOMAIN_WEIGHTS
    ]
    if not measured:
        return None
    return round(
        sum(value * weight for value, weight in measured)
        / sum(weight for _, weight in measured)
    )


def _utc_timestamp(timestamp):
    value = str(timestamp or "")
    for date_format in ("%Y-%m-%d %H:%M:%S:%f", "%Y-%m-%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(value, date_format)
            return f"{parsed.isoformat(timespec='milliseconds')}Z"
        except ValueError:
            continue
    return value


def _analytics_by_module(result_rows):
    analytics = {}
    for row in result_rows:
        metric_group = str(row.get("metric_group") or "")
        if row.get("status") != "COMPUTED" or metric_group not in {"summary", "domains"}:
            continue
        module_name = str(row.get("module_api_name") or "")
        if not module_name:
            continue
        try:
            aggregate = json.loads(row.get("aggregate_json") or "")
        except (TypeError, ValueError, json.JSONDecodeError):
            LOGGER.warning("Skipping invalid trend aggregate result_id=%s", row.get("result_id"))
            continue
        if not isinstance(aggregate, dict):
            continue
        candidate = {
            "computedAt": str(row.get("computed_at") or ""),
            "data": aggregate,
            "sourceRecordCount": _integer(row.get("source_record_count")),
        }
        module = analytics.setdefault(module_name, {})
        existing = module.get(metric_group)
        if existing is None or candidate["computedAt"] >= existing["computedAt"]:
            module[metric_group] = candidate
    return analytics


def _build_point(scan_row, analytics, modules):
    if any("summary" not in analytics.get(module, {}) for module in modules):
        return None

    totals = {
        "recordCount": 0,
        "totalCells": 0,
        "populatedCells": 0,
        "checkedValues": 0,
        "invalidValues": 0,
        "duplicateObservations": 0,
        "duplicateOccurrences": 0,
        "plausibilityChecks": 0,
        "plausibilityFailures": 0,
        "freshnessRecords": 0,
        "freshnessPoints": 0,
        "integrityChecks": 0,
        "integrityFailures": 0,
    }
    for module in modules:
        summary = analytics[module]["summary"]
        data = summary["data"]
        totals["recordCount"] += _integer(
            data.get("recordCount", summary["sourceRecordCount"])
        )
        for key in ("totalCells", "populatedCells", "checkedValues", "invalidValues"):
            totals[key] += _integer(data.get(key))
        domain_result = analytics[module].get("domains")
        domains = domain_result["data"].get("domains", {}) if domain_result else {}
        duplication = domains.get("duplication") or {}
        if duplication.get("applicable"):
            totals["duplicateObservations"] += _integer(duplication.get("observations"))
            totals["duplicateOccurrences"] += _integer(
                duplication.get("duplicateOccurrences")
            )
        plausibility = domains.get("plausibility") or {}
        if plausibility.get("applicable"):
            totals["plausibilityChecks"] += _integer(
                plausibility.get("checksPerformed")
            )
            totals["plausibilityFailures"] += _integer(
                plausibility.get("checksFailed")
            )
        freshness = domains.get("freshness") or {}
        if freshness.get("applicable"):
            totals["freshnessRecords"] += _integer(freshness.get("recordsEvaluated"))
            totals["freshnessPoints"] += _integer(freshness.get("scorePoints"))
        integrity = domains.get("integrity") or {}
        if integrity.get("applicable"):
            totals["integrityChecks"] += _integer(integrity.get("checksPerformed"))
            totals["integrityFailures"] += _integer(integrity.get("checksFailed"))

    completeness = (
        round(totals["populatedCells"] * 100 / totals["totalCells"])
        if totals["totalCells"]
        else None
    )
    validity = (
        round(
            (totals["checkedValues"] - totals["invalidValues"])
            * 100
            / totals["checkedValues"]
        )
        if totals["checkedValues"]
        else None
    )
    domain_scores = {
        "completeness": completeness,
        "duplication": (
            round(
                100
                * (totals["duplicateObservations"] - totals["duplicateOccurrences"])
                / totals["duplicateObservations"]
            )
            if totals["duplicateObservations"]
            else None
        ),
        "validity": validity,
        "plausibility": (
            round(
                100
                * (totals["plausibilityChecks"] - totals["plausibilityFailures"])
                / totals["plausibilityChecks"]
            )
            if totals["plausibilityChecks"]
            else None
        ),
        "freshness": (
            round(totals["freshnessPoints"] / totals["freshnessRecords"])
            if totals["freshnessRecords"]
            else None
        ),
        "integrity": (
            round(
                100
                * (totals["integrityChecks"] - totals["integrityFailures"])
                / totals["integrityChecks"]
            )
            if totals["integrityChecks"]
            else None
        ),
    }
    overall = _score(domain_scores)
    if overall is None:
        return None

    timestamp = _utc_timestamp(
        scan_row.get("completed_at") or scan_row.get("CREATEDTIME") or ""
    )
    return {
        "scanId": scan_row.get("scan_id"),
        "timestamp": timestamp,
        "score": overall,
        "recordCount": totals["recordCount"],
        **domain_scores,
        "measuredDomains": sorted(
            domain for domain, score in domain_scores.items() if score is not None
        ),
    }


def get_scan_trend(request, datastore, scan_id):
    """Return comparable, stored quality points up to the selected scan."""
    del datastore
    try:
        zcql = zcatalyst_sdk.initialize().zcql()
        anchor = find_owned_scan(zcql, scan_id, get_current_user_id(request))
        if not anchor:
            return json_response(
                {"error": {"code": "SCAN_NOT_FOUND", "message": "Scan was not found"}},
                404,
            )

        anchor_analytics = _analytics_by_module(find_analytics_results(zcql, anchor["ROWID"]))
        available_modules = sorted(
            module for module, values in anchor_analytics.items() if "summary" in values
        )
        requested_modules = sorted(
            {
                str(module).strip()
                for module in query_list_values(request, "module")
                if str(module).strip()
            }
        )
        modules = requested_modules or available_modules
        if set(modules) - set(available_modules):
            return json_response(
                {
                    "error": {
                        "code": "TREND_MODULE_NOT_IN_SCAN",
                        "message": "Trend modules must belong to the selected scan",
                    }
                },
                400,
            )

        connection_row_id = int(foreign_row_id(anchor.get("connection_row_id")))
        safe_clock = str(anchor.get("clock_field") or "").replace("'", "''")
        safe_depth = str(anchor.get("depth_policy") or "").replace("'", "''")
        candidates = _rows(
            zcql,
            "select * from scan_jobs where "
            f"connection_row_id = {connection_row_id} "
            "and status = 'COMPLETED' "
            f"and clock_field = '{safe_clock}' "
            f"and depth_policy = '{safe_depth}' "
            "order by CREATEDTIME desc limit 50",
            "scan_jobs",
        )

        anchor_point = _build_point(anchor, anchor_analytics, modules)
        if anchor_point is None:
            return json_response(
                {
                    "scanId": scan_id,
                    "criteria": {
                        "clock": anchor.get("clock_field"),
                        "depth": anchor.get("depth_policy"),
                        "modules": modules,
                    },
                    "series": [],
                    "moduleSeries": [],
                    "skippedUnmeasuredCount": 0,
                }
            )
        required_domains = set(anchor_point["measuredDomains"])
        module_anchor_points = {
            module: _build_point(anchor, anchor_analytics, [module])
            for module in modules
        }
        module_required_domains = {
            module: set(point["measuredDomains"])
            for module, point in module_anchor_points.items()
            if point is not None
        }
        anchor_timestamp = str(anchor.get("completed_at") or anchor.get("CREATEDTIME") or "")
        points = []
        module_points = {module: [] for module in modules}
        skipped = 0
        for candidate in candidates:
            candidate_timestamp = str(
                candidate.get("completed_at") or candidate.get("CREATEDTIME") or ""
            )
            if anchor_timestamp and candidate_timestamp > anchor_timestamp:
                continue
            analytics = _analytics_by_module(
                find_analytics_results(zcql, candidate["ROWID"])
            )
            point = _build_point(candidate, analytics, modules)
            if point is None or set(point["measuredDomains"]) != required_domains:
                skipped += 1
            else:
                points.append(point)
            for module in modules:
                if module not in module_required_domains:
                    continue
                module_point = _build_point(candidate, analytics, [module])
                if (
                    module_point is not None
                    and set(module_point["measuredDomains"])
                    == module_required_domains[module]
                ):
                    module_points[module].append(module_point)

        points.sort(key=lambda point: (point["timestamp"], point["scanId"] or ""))
        for series in module_points.values():
            series.sort(key=lambda point: (point["timestamp"], point["scanId"] or ""))
        return json_response(
            {
                "scanId": scan_id,
                "criteria": {
                    "clock": anchor.get("clock_field"),
                    "depth": anchor.get("depth_policy"),
                    "modules": modules,
                },
                "series": points[-MAX_TREND_POINTS:],
                "moduleSeries": [
                    {
                        "moduleApiName": module,
                        "series": module_points[module][-MAX_TREND_POINTS:],
                    }
                    for module in modules
                ],
                "skippedUnmeasuredCount": skipped,
            }
        )
    except AuthenticationRequired:
        raise
    except Exception as exc:  # noqa: BLE001 - keep datastore details server-side
        LOGGER.exception("Could not read scan trend scan_id=%s: %s", scan_id, exc)
        return json_response(
            {
                "error": {
                    "code": "SCAN_TREND_READ_FAILED",
                    "message": "Scan trend could not be read",
                }
            },
            500,
        )
