from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping

from .states import RecordState


@dataclass(frozen=True)
class MinimizedRecordFinding:
    """The literal D7 record tuple; deliberately excludes scan/job linkage."""

    record_id: str
    module: str
    state: RecordState
    rule_ids: tuple[str, ...] = ()
    reason_ids: tuple[str, ...] = ()
    duplicate_partner_reference: str | None = None
    duplicate_confidence: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.record_id or not self.module:
            raise ValueError("Record ID and module are required")
        if self.duplicate_confidence is not None and not (
            Decimal(0) <= self.duplicate_confidence <= Decimal(1)
        ):
            raise ValueError("Duplicate confidence must be between 0 and 1")

    def export_row(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "module": self.module,
            "state": self.state.value,
            "rule_ids": list(self.rule_ids),
            "reason_ids": list(self.reason_ids),
            "duplicate_partner_reference": self.duplicate_partner_reference,
            "duplicate_confidence": (
                str(self.duplicate_confidence)
                if self.duplicate_confidence is not None
                else None
            ),
        }


FORBIDDEN_PERSISTED_KEYS = frozenset(
    {
        "name",
        "label",
        "stage",
        "email",
        "phone",
        "strong_id",
        "statutory_id",
        "blocking_key",
        "normalized_email",
        "normalized_phone",
        "source_timestamp",
        "created_time",
        "modified_time",
        "user_id",
        "user_token",
        "dimension_key",
        "bucket_key",
    }
)


def forbidden_persisted_paths(value: Any, path: str = "$") -> tuple[str, ...]:
    """Find obvious D7-forbidden keys in a proposed persisted/log/export payload."""
    findings: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key).lower() in FORBIDDEN_PERSISTED_KEYS:
                findings.append(child_path)
            findings.extend(forbidden_persisted_paths(child, child_path))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            findings.extend(forbidden_persisted_paths(child, f"{path}[{index}]"))
    return tuple(findings)
