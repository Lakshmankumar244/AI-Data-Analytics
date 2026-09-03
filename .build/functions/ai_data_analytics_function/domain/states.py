from enum import Enum
from typing import Iterable


class RecordState(str, Enum):
    PROPER = "proper"
    INCOMPLETE = "incomplete"
    INACCURATE = "inaccurate"
    SUSPICIOUS = "suspicious"
    SUSPECTED_DUPLICATE = "suspected_duplicate"
    CONFIRMED_DUPLICATE = "confirmed_duplicate"


_PRECEDENCE = {
    state: rank
    for rank, state in enumerate(
        (
            RecordState.PROPER,
            RecordState.INCOMPLETE,
            RecordState.INACCURATE,
            RecordState.SUSPICIOUS,
            RecordState.SUSPECTED_DUPLICATE,
            RecordState.CONFIRMED_DUPLICATE,
        )
    )
}


def terminal_state(states: Iterable[RecordState]) -> RecordState:
    """Return the highest D3 state without discarding underlying findings."""
    materialized = tuple(states)
    if not materialized:
        return RecordState.PROPER
    return max(materialized, key=_PRECEDENCE.__getitem__)

