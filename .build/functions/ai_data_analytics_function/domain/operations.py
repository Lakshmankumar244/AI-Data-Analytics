from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Hashable, Iterable, TypeVar


T = TypeVar("T")


def group_nonblank_values(
    records: Iterable[T], value_of: Callable[[T], str | None]
) -> dict[str, tuple[T, ...]]:
    """D6-compatible grouping: blank phone/email values never form a group."""
    grouped: dict[str, list[T]] = defaultdict(list)
    for record in records:
        value = value_of(record)
        if value is None or not value.strip():
            continue
        grouped[value].append(record)
    return {key: tuple(values) for key, values in grouped.items()}


def combined_action_gain(
    baseline: T,
    selected_actions: Iterable[Hashable],
    apply_combined: Callable[[T, tuple[Hashable, ...]], T],
    score: Callable[[T], Decimal],
) -> Decimal:
    """D16: apply the selection together and rescore once; never sum action gains."""
    actions = tuple(selected_actions)
    baseline_score = score(baseline)
    combined_candidate = apply_combined(baseline, actions)
    return score(combined_candidate) - baseline_score


@dataclass
class ApiStats:
    dispatched: int = 0
    completed: int = 0
    retried: int = 0
    failed: int = 0

    @classmethod
    def for_new_scan(cls) -> "ApiStats":
        """D17 requires a fresh counter set for every scan run."""
        return cls()
