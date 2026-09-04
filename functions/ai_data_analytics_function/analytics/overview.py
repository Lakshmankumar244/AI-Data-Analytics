"""Overview extras derived from stored aggregates and the prior comparable scan."""

import logging

from analytics.repository import find_analytics_results
from analytics.service import build_results
from analytics.trends import _analytics_by_module, _build_point, _rows
from common.core import foreign_row_id


LOGGER = logging.getLogger(__name__)
MOVER_LIMIT = 5
MIN_RECORDS_PER_USER = 25
OWNER_SCORE_WEIGHTS = {"completeness": 20, "validity": 15}
RECORD_STATES = (
    "proper",
    "incomplete",
    "inaccurate",
    "suspicious",
    "suspected_duplicate",
    "confirmed_duplicate",
)


def _integer(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _empty_states():
    return {state: 0 for state in RECORD_STATES}


def _label(api_name):
    words = str(api_name or "").replace("_", " ").strip()
    if not words:
        return "Module"
    return " ".join(word[:1].upper() + word[1:] for word in words.split())


def _percent(part, whole):
    if not whole:
        return None
    return round(part * 100 / whole)


def _owner_score(data):
    completeness = _percent(
        _integer(data.get("populatedCells")), _integer(data.get("totalCells"))
    )
    validity = None
    checked = _integer(data.get("checkedValues"))
    if checked:
        validity = _percent(checked - _integer(data.get("invalidValues")), checked)
    measured = [
        (score, OWNER_SCORE_WEIGHTS[domain])
        for domain, score in (("completeness", completeness), ("validity", validity))
        if score is not None
    ]
    if not measured:
        return None
    return round(
        sum(score * weight for score, weight in measured)
        / sum(weight for _, weight in measured)
    )


def _module_record_count(module):
    summary = (module.get("metrics") or {}).get("summary") or {}
    data = summary.get("data") or {}
    return _integer(data.get("recordCount", module.get("sourceRecordCount")))


def _state_counts_from_findings(module):
    findings = ((module.get("metrics") or {}).get("record_findings") or {}).get("data")
    if not isinstance(findings, dict) or not findings.get("measured"):
        return None
    stored = findings.get("stateCounts")
    if isinstance(stored, dict) and "proper" in stored:
        return {state: _integer(stored.get(state)) for state in RECORD_STATES}

    records = _module_record_count(module)
    affected = _integer(findings.get("affectedRecordCount"))
    missing = _integer(findings.get("missingIssueCount"))
    invalid = _integer(findings.get("invalidIssueCount"))
    counts = _empty_states()
    counts["proper"] = max(0, records - affected)
    if affected <= 0:
        return counts
    if invalid == 0:
        counts["incomplete"] = affected
        return counts
    if missing == 0:
        counts["inaccurate"] = affected
        return counts
    # Older scans store issue totals, not exclusive record states. All
    # affected records have quality issues; keep the buckets additive.
    counts["incomplete"] = affected
    return counts


def _state_breakdown(modules):
    totals = _empty_states()
    measured = False
    for module in modules:
        counts = _state_counts_from_findings(module)
        if counts is None:
            continue
        measured = True
        for state in RECORD_STATES:
            totals[state] += counts[state]
    return totals if measured else None


def _created_in_period(modules):
    return [
        {
            "moduleApiName": module.get("moduleApiName"),
            "label": _label(module.get("moduleApiName")),
            "recordCount": _module_record_count(module),
        }
        for module in modules
        if module.get("moduleApiName")
    ]


def _owners_by_key(modules):
    grouped = {}
    for module in modules:
        for result in module.get("ownerAnalytics") or []:
            data = result.get("data") or {}
            owner_key = str(data.get("ownerKey") or "")
            if not owner_key:
                continue
            owner = grouped.setdefault(
                owner_key,
                {
                    "ownerKey": owner_key,
                    "ownerName": str(data.get("ownerName") or "Unassigned"),
                    "recordCount": 0,
                    "totalCells": 0,
                    "populatedCells": 0,
                    "checkedValues": 0,
                    "invalidValues": 0,
                },
            )
            for key in (
                "recordCount",
                "totalCells",
                "populatedCells",
                "checkedValues",
                "invalidValues",
            ):
                owner[key] += _integer(data.get(key))
    for owner in grouped.values():
        owner["score"] = _owner_score(owner)
    return grouped


def _module_points(scan_row, analytics, modules):
    points = {}
    for module in modules:
        point = _build_point(scan_row, analytics, [module])
        if point is not None:
            points[module] = point
    return points


def _prior_scan_row(zcql, scan_row):
    connection_row_id = foreign_row_id(scan_row.get("connection_row_id"))
    if not str(connection_row_id or "").isdigit():
        return None
    safe_clock = str(scan_row.get("clock_field") or "").replace("'", "''")
    safe_depth = str(scan_row.get("depth_policy") or "").replace("'", "''")
    candidates = _rows(
        zcql,
        "select * from scan_jobs where "
        f"connection_row_id = {int(connection_row_id)} "
        "and status = 'COMPLETED' "
        f"and clock_field = '{safe_clock}' "
        f"and depth_policy = '{safe_depth}' "
        "order by CREATEDTIME desc limit 50",
        "scan_jobs",
    )
    anchor_id = str(scan_row.get("scan_id") or "")
    anchor_timestamp = str(
        scan_row.get("completed_at") or scan_row.get("CREATEDTIME") or ""
    )
    for candidate in candidates:
        if str(candidate.get("scan_id") or "") == anchor_id:
            continue
        candidate_timestamp = str(
            candidate.get("completed_at") or candidate.get("CREATEDTIME") or ""
        )
        if anchor_timestamp and candidate_timestamp > anchor_timestamp:
            continue
        return candidate
    return None


def _build_movers(scan_row, modules, current_analytics, prior_row, prior_modules):
    movers = []
    current_names = [
        module.get("moduleApiName") for module in modules if module.get("moduleApiName")
    ]
    prior_analytics = {}
    for module in prior_modules:
        name = str(module.get("moduleApiName") or "")
        metrics = module.get("metrics") or {}
        if not name:
            continue
        converted = {}
        for metric_group in ("summary", "domains"):
            payload = metrics.get(metric_group)
            if not payload:
                continue
            converted[metric_group] = {
                "data": payload.get("data") or {},
                "sourceRecordCount": _integer(module.get("sourceRecordCount")),
            }
        if converted:
            prior_analytics[name] = converted

    current_points = _module_points(scan_row, current_analytics, current_names)
    prior_points = _module_points(prior_row, prior_analytics, current_names)
    for module_name, current in current_points.items():
        prior = prior_points.get(module_name)
        if prior is None or current.get("score") is None or prior.get("score") is None:
            continue
        delta = int(current["score"]) - int(prior["score"])
        if delta == 0:
            continue
        movers.append(
            {
                "type": "module",
                "key": module_name,
                "label": _label(module_name),
                "delta": delta,
            }
        )

    current_owners = _owners_by_key(modules)
    prior_owners = _owners_by_key(prior_modules)
    for owner_key, current in current_owners.items():
        prior = prior_owners.get(owner_key)
        if not prior:
            continue
        if (
            current["recordCount"] < MIN_RECORDS_PER_USER
            or prior["recordCount"] < MIN_RECORDS_PER_USER
        ):
            continue
        if current["score"] is None or prior["score"] is None:
            continue
        delta = int(current["score"]) - int(prior["score"])
        if delta == 0:
            continue
        movers.append(
            {
                "type": "user",
                "key": owner_key,
                "label": current["ownerName"] or "Unassigned",
                "delta": delta,
            }
        )

    movers.sort(key=lambda item: (-abs(item["delta"]), item["label"].lower()))
    return movers[:MOVER_LIMIT]


def build_overview(zcql, scan_row, result_rows, modules):
    current_analytics = _analytics_by_module(result_rows)
    created_in_period = _created_in_period(modules)
    state_breakdown = _state_breakdown(modules)
    prior_score = None
    movers = []

    try:
        prior_row = _prior_scan_row(zcql, scan_row)
        if prior_row:
            prior_result_rows = find_analytics_results(zcql, prior_row["ROWID"])
            prior_modules = build_results(prior_row, prior_result_rows).get("modules") or []
            shared = [
                module["moduleApiName"]
                for module in modules
                if module.get("moduleApiName")
                and "summary" in current_analytics.get(module["moduleApiName"], {})
                and "summary" in _analytics_by_module(prior_result_rows).get(
                    module["moduleApiName"], {}
                )
            ]
            if shared:
                prior_point = _build_point(
                    prior_row, _analytics_by_module(prior_result_rows), shared
                )
                if prior_point is not None:
                    prior_score = prior_point.get("score")
            movers = _build_movers(
                scan_row, modules, current_analytics, prior_row, prior_modules
            )
    except Exception as exc:  # noqa: BLE001 - overview extras must not fail results
        LOGGER.warning(
            "Could not compare prior scan for overview scan_id=%s: %s",
            scan_row.get("scan_id"),
            exc,
        )

    return {
        "priorScore": prior_score,
        "stateBreakdown": state_breakdown,
        "createdInPeriod": created_in_period,
        "movers": movers,
    }
