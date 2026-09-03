"""Run matrix-authorized synthetic verification work without product behavior.

Nothing in this file is a production schema, collector, OAuth flow, or fallback.
"""

import itertools
import json
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
FUNCTION_ROOT = ROOT / "functions" / "ai_data_analytics_function"
sys.path.insert(0, str(FUNCTION_ROOT))

from domain.authorization import validate_explicit_read_scopes
from domain.privacy import forbidden_persisted_paths
from domain.scoring import RuleObservation, severity_weighted_domain_score
from domain.time_policy import in_organization_timezone


def verify_chunk_coverage() -> dict[str, object]:
    """Prove the proposed fixed-chunk matrix misses no pair in oversized blocks."""
    results = {}
    for size in (41, 81, 101):
        records = tuple(str(index) for index in range(size))
        chunks = tuple(records[index : index + 40] for index in range(0, size, 40))
        observed: set[tuple[str, str]] = set()
        for left_index, left_chunk in enumerate(chunks):
            for right_index in range(left_index, len(chunks)):
                right_chunk = chunks[right_index]
                for left in left_chunk:
                    for right in right_chunk:
                        if left == right:
                            continue
                        observed.add(tuple(sorted((left, right), key=int)))
        expected = {
            tuple(sorted(pair, key=int))
            for pair in itertools.combinations(records, 2)
        }
        if observed != expected:
            raise AssertionError(f"Chunk plan missed pairs for block size {size}")
        results[str(size)] = len(observed)
    return {"status": "PASS", "pair_counts": results}


def verify_checkpoint_idempotency() -> dict[str, object]:
    """Exercise crash/resume logic with synthetic temporary SQLite state.

    The schema deliberately disappears when the temporary directory is removed and
    must not be copied into Catalyst without D7 product approval and platform proof.
    """
    with tempfile.TemporaryDirectory(prefix="d13-synthetic-") as directory:
        database = Path(directory) / "checkpoint.sqlite"
        connection = sqlite3.connect(database)
        connection.executescript(
            """
            CREATE TABLE synthetic_batch (
                batch_key TEXT PRIMARY KEY,
                status TEXT NOT NULL
            );
            CREATE TABLE synthetic_fact (
                batch_key TEXT NOT NULL,
                record_id TEXT NOT NULL,
                module TEXT NOT NULL,
                state TEXT NOT NULL,
                rule_id TEXT NOT NULL,
                PRIMARY KEY (batch_key, record_id, rule_id)
            );
            """
        )
        batches = {
            "batch-1": (("1", "proper", ""), ("2", "incomplete", "r1")),
            "batch-2": (("3", "proper", ""), ("4", "suspicious", "r2")),
        }
        connection.executemany(
            "INSERT INTO synthetic_batch(batch_key, status) VALUES (?, 'PLANNED')",
            ((key,) for key in batches),
        )
        connection.commit()

        def commit_batch(batch_key: str) -> None:
            for record_id, state, rule_id in batches[batch_key]:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO synthetic_fact
                        (batch_key, record_id, module, state, rule_id)
                    VALUES (?, ?, 'SyntheticModule', ?, ?)
                    """,
                    (batch_key, record_id, state, rule_id),
                )
            connection.execute(
                "UPDATE synthetic_batch SET status = 'VERIFIED' WHERE batch_key = ?",
                (batch_key,),
            )
            connection.commit()

        commit_batch("batch-1")
        connection.close()  # simulated worker death after a durable checkpoint

        connection = sqlite3.connect(database)
        pending = tuple(
            row[0]
            for row in connection.execute(
                "SELECT batch_key FROM synthetic_batch WHERE status != 'VERIFIED'"
            )
        )
        if pending != ("batch-2",):
            raise AssertionError(f"Unexpected resume set: {pending}")
        commit_batch("batch-1")  # at-least-once retry must not duplicate facts
        commit_batch("batch-2")
        fact_count = connection.execute(
            "SELECT COUNT(*) FROM synthetic_fact"
        ).fetchone()[0]
        verified_count = connection.execute(
            "SELECT COUNT(*) FROM synthetic_batch WHERE status = 'VERIFIED'"
        ).fetchone()[0]
        connection.close()
        if fact_count != 4 or verified_count != 2:
            raise AssertionError("Synthetic resume produced lost or duplicate facts")
        return {
            "status": "PASS",
            "verified_batches": verified_count,
            "unique_facts": fact_count,
        }


def verify_timezone_conversion() -> dict[str, object]:
    before_fallback = datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc)
    after_fallback = datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc)
    before_local = in_organization_timezone(before_fallback, "America/New_York")
    after_local = in_organization_timezone(after_fallback, "America/New_York")
    if before_local.hour != 1 or after_local.hour != 1:
        raise AssertionError("DST overlap conversion did not preserve both local 01:30s")
    if before_local.utcoffset() == after_local.utcoffset():
        raise AssertionError("DST overlap did not produce distinct UTC offsets")

    india = in_organization_timezone(
        datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc), "Asia/Kolkata"
    )
    if str(india.utcoffset()) != "5:30:00":
        raise AssertionError("Asia/Kolkata mapping was not +05:30")
    return {
        "status": "PASS",
        "dst_offsets": [str(before_local.utcoffset()), str(after_local.utcoffset())],
        "kolkata_offset": str(india.utcoffset()),
    }


def verify_scope_and_privacy_guards() -> dict[str, object]:
    validate_explicit_read_scopes(
        ("ZohoCRM.org.READ", "ZohoCRM.modules.leads.READ")
    )
    create_rejected = False
    try:
        validate_explicit_read_scopes(("ZohoCRM.bulk.CREATE",))
    except ValueError:
        create_rejected = True
    if not create_rejected:
        raise AssertionError("CREATE scope was not rejected")

    safe_payload = {
        "record_id": "synthetic-1",
        "module": "SyntheticModule",
        "state": "proper",
        "rule_ids": [],
        "reason_ids": [],
    }
    unsafe_payload = {**safe_payload, "stage": "SyntheticStage"}
    if forbidden_persisted_paths(safe_payload):
        raise AssertionError("Safe D7 tuple produced a leakage finding")
    leaks = forbidden_persisted_paths(unsafe_payload)
    if leaks != ("$.stage",):
        raise AssertionError(f"D7 leakage was not detected: {leaks}")
    return {"status": "PASS", "create_scope_rejected": True, "detected": leaks}


def verify_decimal_determinism() -> dict[str, object]:
    observations = (
        RuleObservation("critical", "critical", 7, 2),
        RuleObservation("medium", "medium", 9, 4),
        RuleObservation("info", "info", 11, 3),
    )
    results = {severity_weighted_domain_score(observations) for _ in range(100)}
    if len(results) != 1:
        raise AssertionError("D2 Decimal calculation was not deterministic")
    score = results.pop()
    return {"status": "PASS", "exact_decimal": str(score)}


def main() -> int:
    report = {
        "synthetic_verifications": {
            "d5_chunk_coverage": verify_chunk_coverage(),
            "d13_checkpoint_idempotency": verify_checkpoint_idempotency(),
            "tz1_timezone_conversion": verify_timezone_conversion(),
            "d7_d14_guards": verify_scope_and_privacy_guards(),
            "d2_decimal_determinism": verify_decimal_determinism(),
        },
        "not_run_without_external_sandbox": [
            "D14-EVIDENCE org visibility, scope introspection, sharing, roles, territories",
            "Zoho CRM administrator-status proof",
            "Bulk Read/COQL real scopes, limits, paging, expiry, credits and visibility",
            "Catalyst transaction, scheduler, callback and ephemeral-storage guarantees",
            "module-specific genuine close/audit timestamp availability",
        ],
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
