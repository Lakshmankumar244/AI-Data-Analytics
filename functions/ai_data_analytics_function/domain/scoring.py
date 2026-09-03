from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Iterable

from .errors import ProductApprovalRequired


SEVERITY_WEIGHTS = {
    "critical": Decimal("3"),
    "high": Decimal("2.5"),
    "medium": Decimal("2"),
    "low": Decimal("1.5"),
    "info": Decimal("1"),
}


@dataclass(frozen=True)
class RuleObservation:
    rule_id: str
    severity: str
    eligible: int
    offending: int

    def __post_init__(self) -> None:
        if self.severity not in SEVERITY_WEIGHTS:
            raise ValueError(f"Unknown severity: {self.severity}")
        if self.eligible < 0 or self.offending < 0:
            raise ValueError("Observation counts cannot be negative")
        if self.offending > self.eligible:
            raise ValueError("Offending count cannot exceed eligible count")


@dataclass(frozen=True)
class DomainScore:
    domain_id: str
    score: Decimal
    domain_weight: Decimal
    applicable: bool = True
    measurable: bool = True


def percent_clean(proper_records: int, total_records: int) -> Decimal:
    """D4 properPct only; the unresolved minimum floor is not applied here."""
    if proper_records < 0 or total_records < 0:
        raise ValueError("Record counts cannot be negative")
    if proper_records > total_records:
        raise ValueError("Proper records cannot exceed total records")
    if total_records == 0:
        raise ValueError("Percent clean is undefined for zero records")
    with localcontext() as context:
        context.prec = 28
        return Decimal(100) * Decimal(proper_records) / Decimal(total_records)


def severity_weighted_domain_score(
    observations: Iterable[RuleObservation],
) -> Decimal:
    """Calculate the approved D2 domain formula without inventing zero-eligible behavior."""
    rules = tuple(observations)
    if not rules:
        raise ProductApprovalRequired(
            "The contract does not define a domain with no rule observations"
        )
    if any(rule.eligible == 0 for rule in rules):
        raise ProductApprovalRequired(
            "The contract does not define zero-eligible rule behavior"
        )

    with localcontext() as context:
        context.prec = 28
        weighted_pass_rates = Decimal(0)
        total_weight = Decimal(0)
        for rule in rules:
            weight = SEVERITY_WEIGHTS[rule.severity]
            pass_rate = Decimal(1) - Decimal(rule.offending) / Decimal(rule.eligible)
            weighted_pass_rates += weight * pass_rate
            total_weight += weight
        return Decimal(100) * weighted_pass_rates / total_weight


def applicable_overall_score(
    domains: Iterable[DomainScore], *, d12_resolved_and_revalidated: bool
) -> Decimal:
    """Exercise D2 normalization while refusing to choose D12 treatment."""
    if not d12_resolved_and_revalidated:
        raise ProductApprovalRequired(
            "D12 must be resolved and D2 revalidated before overall scoring"
        )

    included = tuple(
        domain for domain in domains if domain.applicable and domain.measurable
    )
    if not included:
        raise ValueError("No applicable, measurable domain is available")
    if any(domain.domain_weight <= 0 for domain in included):
        raise ValueError("Included domain weights must be positive")

    with localcontext() as context:
        context.prec = 28
        numerator = sum(
            (domain.domain_weight * domain.score for domain in included), Decimal(0)
        )
        denominator = sum(
            (domain.domain_weight for domain in included), Decimal(0)
        )
        return numerator / denominator

