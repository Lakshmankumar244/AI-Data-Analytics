from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from .errors import ProductApprovalRequired


class DuplicateState(str, Enum):
    SUSPECTED = "suspected_duplicate"
    CONFIRMED = "confirmed_duplicate"


@dataclass(frozen=True)
class PairEvidence:
    confidence: Decimal
    exact_strong_field_count: int
    exact_strong_identifier: bool = False
    exact_email: bool = False
    exact_phone: bool = False

    def __post_init__(self) -> None:
        if not Decimal(0) <= self.confidence <= Decimal(1):
            raise ValueError("Confidence must be between 0 and 1")
        if self.exact_strong_field_count < 0:
            raise ValueError("Exact strong-field count cannot be negative")


def classify_pair(evidence: PairEvidence) -> DuplicateState | None:
    """Apply only D5 confirmation/band behavior explicitly authorized by the matrix."""
    if evidence.exact_strong_identifier:
        return DuplicateState.CONFIRMED
    if evidence.exact_email and evidence.exact_phone:
        return DuplicateState.CONFIRMED
    if (
        evidence.confidence >= Decimal("0.90")
        and evidence.exact_strong_field_count >= 2
    ):
        return DuplicateState.CONFIRMED
    if Decimal("0.70") <= evidence.confidence < Decimal("0.90"):
        return DuplicateState.SUSPECTED
    if evidence.confidence >= Decimal("0.90"):
        raise ProductApprovalRequired(
            "The contract does not assign a fallback state at >=0.90 without two "
            "exact strong-field agreements"
        )
    return None


def normalized_name_prefix_key(module: str, normalized_name: str) -> str | None:
    """Build D5.4's key from an already-authoritatively-normalized name.

    Name normalization is intentionally not implemented here because the matrix first
    requires confirmation of the authoritative spec file/version.
    """
    if not module:
        raise ValueError("Module is required")
    if not normalized_name:
        return None
    return f"{module}|nm|{normalized_name[:8]}"


def duplicate_action(state: DuplicateState) -> str:
    if state is DuplicateState.SUSPECTED:
        return "review-duplicates"
    return "merge-duplicates"

