import sys
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


FUNCTION_ROOT = (
    Path(__file__).resolve().parents[1]
    / "functions"
    / "ai_data_analytics_function"
)
sys.path.insert(0, str(FUNCTION_ROOT))

from domain.authorization import validate_explicit_read_scopes
from domain.duplicates import (
    DuplicateState,
    PairEvidence,
    classify_pair,
    duplicate_action,
    normalized_name_prefix_key,
)
from domain.errors import ProductApprovalRequired, TechnicalVerificationRequired
from domain.operations import ApiStats, combined_action_gain, group_nonblank_values
from domain.privacy import MinimizedRecordFinding, forbidden_persisted_paths
from domain.scoring import (
    DomainScore,
    RuleObservation,
    applicable_overall_score,
    percent_clean,
    severity_weighted_domain_score,
)
from domain.states import RecordState, terminal_state
from domain.time_policy import (
    CloseTimestampStatus,
    MODIFIED_TIME_DISCLOSURE,
    in_organization_timezone,
    resolve_close_timestamp,
)


class ScoringTests(unittest.TestCase):
    def test_d2_severity_weighted_domain_score(self):
        score = severity_weighted_domain_score(
            (
                RuleObservation("critical-rule", "critical", 10, 2),
                RuleObservation("info-rule", "info", 10, 5),
            )
        )
        self.assertEqual(score, Decimal("72.500"))

    def test_d2_counts_multiple_rule_observations(self):
        score = severity_weighted_domain_score(
            (
                RuleObservation("rule-a", "high", 1, 1),
                RuleObservation("rule-b", "high", 1, 1),
            )
        )
        self.assertEqual(score, Decimal("0"))

    def test_zero_eligible_stops_at_product_boundary(self):
        with self.assertRaises(ProductApprovalRequired):
            severity_weighted_domain_score(
                (RuleObservation("unknown-applicability", "low", 0, 0),)
            )

    def test_overall_score_refuses_to_choose_d12(self):
        domains = (DomainScore("validity", Decimal("80"), Decimal("15")),)
        with self.assertRaises(ProductApprovalRequired):
            applicable_overall_score(
                domains, d12_resolved_and_revalidated=False
            )

    def test_overall_normalization_excludes_explicitly_unmeasurable_domains(self):
        domains = (
            DomainScore("validity", Decimal("80"), Decimal("15")),
            DomainScore(
                "pii-access",
                Decimal("0"),
                Decimal("4"),
                measurable=False,
            ),
        )
        self.assertEqual(
            applicable_overall_score(
                domains, d12_resolved_and_revalidated=True
            ),
            Decimal("80"),
        )

    def test_d4_percent_clean_has_no_inferred_floor(self):
        self.assertEqual(percent_clean(3, 4), Decimal("75"))


class StateAndOperationTests(unittest.TestCase):
    def test_d3_precedence(self):
        self.assertEqual(
            terminal_state(
                (
                    RecordState.INCOMPLETE,
                    RecordState.SUSPICIOUS,
                    RecordState.INACCURATE,
                )
            ),
            RecordState.SUSPICIOUS,
        )

    def test_d6_blank_values_are_not_grouped(self):
        records = (
            {"id": "1", "phone": ""},
            {"id": "2", "phone": "  "},
            {"id": "3", "phone": None},
            {"id": "4", "phone": "999"},
            {"id": "5", "phone": "999"},
        )
        grouped = group_nonblank_values(records, lambda item: item["phone"])
        self.assertEqual(tuple(grouped), ("999",))
        self.assertEqual(len(grouped["999"]), 2)

    def test_d16_combined_selection_is_scored_once(self):
        calls = {"apply": 0, "score": 0}

        def apply_combined(value, actions):
            calls["apply"] += 1
            return value + len(actions) * 10

        def score(value):
            calls["score"] += 1
            return Decimal(value)

        gain = combined_action_gain(50, ("a", "b"), apply_combined, score)
        self.assertEqual(gain, Decimal("20"))
        self.assertEqual(calls, {"apply": 1, "score": 2})

    def test_d17_stats_reset_per_scan(self):
        first = ApiStats.for_new_scan()
        first.failed = 3
        second = ApiStats.for_new_scan()
        self.assertEqual(second.failed, 0)


class DuplicateTests(unittest.TestCase):
    def test_exact_strong_identifier_confirms(self):
        self.assertEqual(
            classify_pair(
                PairEvidence(
                    Decimal("0.10"), 1, exact_strong_identifier=True
                )
            ),
            DuplicateState.CONFIRMED,
        )

    def test_exact_email_and_phone_confirms(self):
        self.assertEqual(
            classify_pair(
                PairEvidence(
                    Decimal("0.10"), 2, exact_email=True, exact_phone=True
                )
            ),
            DuplicateState.CONFIRMED,
        )

    def test_standard_confirmation_requires_both_conditions(self):
        self.assertEqual(
            classify_pair(PairEvidence(Decimal("0.90"), 2)),
            DuplicateState.CONFIRMED,
        )

    def test_suspected_band_routes_to_review(self):
        state = classify_pair(PairEvidence(Decimal("0.70"), 1))
        self.assertEqual(state, DuplicateState.SUSPECTED)
        self.assertEqual(duplicate_action(state), "review-duplicates")

    def test_unresolved_high_confidence_edge_stops(self):
        with self.assertRaises(ProductApprovalRequired):
            classify_pair(PairEvidence(Decimal("0.95"), 1))

    def test_below_floor_is_not_a_duplicate(self):
        self.assertIsNone(classify_pair(PairEvidence(Decimal("0.69"), 1)))

    def test_name_prefix_accepts_pre_normalized_input_only(self):
        self.assertEqual(
            normalized_name_prefix_key("Leads", "abcdefghijk"),
            "Leads|nm|abcdefgh",
        )


class PrivacyAndAuthorizationTests(unittest.TestCase):
    def test_d7_export_is_literal_minimized_tuple(self):
        row = MinimizedRecordFinding(
            record_id="100",
            module="Leads",
            state=RecordState.SUSPECTED_DUPLICATE,
            rule_ids=("duplication.fuzzy",),
            duplicate_partner_reference="101",
            duplicate_confidence=Decimal("0.80"),
        ).export_row()
        self.assertEqual(forbidden_persisted_paths(row), ())
        self.assertNotIn("scan_id", row)
        self.assertNotIn("batch_id", row)

    def test_d7_leakage_detector_finds_nested_forbidden_values(self):
        proposed = {"record_id": "100", "details": {"email": "x@example.test"}}
        self.assertEqual(forbidden_persisted_paths(proposed), ("$.details.email",))

    def test_only_explicit_read_scopes_are_accepted(self):
        self.assertEqual(
            validate_explicit_read_scopes(
                ("ZohoCRM.org.READ", "ZohoCRM.modules.leads.READ")
            ),
            ("ZohoCRM.org.READ", "ZohoCRM.modules.leads.READ"),
        )

    def test_create_scope_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_explicit_read_scopes(("ZohoCRM.bulk.CREATE",))


class TimePolicyTests(unittest.TestCase):
    def test_genuine_close_timestamp_wins(self):
        genuine = datetime(2026, 1, 1, tzinfo=timezone.utc)
        modified = datetime(2026, 2, 1, tzinfo=timezone.utc)
        result = resolve_close_timestamp(genuine, modified)
        self.assertEqual(result.timestamp, genuine)
        self.assertEqual(result.status, CloseTimestampStatus.VERIFIED_GENUINE)
        self.assertIsNone(result.disclosure)

    def test_modified_time_is_disclosed_approximation(self):
        modified = datetime(2026, 2, 1, tzinfo=timezone.utc)
        result = resolve_close_timestamp(None, modified)
        self.assertEqual(result.timestamp, modified)
        self.assertEqual(
            result.status, CloseTimestampStatus.APPROXIMATION_DISCLOSED
        )
        self.assertEqual(result.disclosure, MODIFIED_TIME_DISCLOSURE)

    def test_unavailable_requires_both_sources_missing(self):
        result = resolve_close_timestamp(None, None)
        self.assertEqual(result.status, CloseTimestampStatus.UNAVAILABLE)

    def test_unknown_timezone_has_no_fallback(self):
        with self.assertRaises(TechnicalVerificationRequired):
            in_organization_timezone(
                datetime(2026, 1, 1, tzinfo=timezone.utc), "Unknown/Nowhere"
            )


if __name__ == "__main__":
    unittest.main()
