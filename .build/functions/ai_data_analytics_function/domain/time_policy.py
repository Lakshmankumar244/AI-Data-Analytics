from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .errors import TechnicalVerificationRequired


class CloseTimestampStatus(str, Enum):
    VERIFIED_GENUINE = "VERIFIED_GENUINE"
    APPROXIMATION_DISCLOSED = "APPROXIMATION_DISCLOSED"
    UNAVAILABLE = "UNAVAILABLE"


MODIFIED_TIME_DISCLOSURE = (
    "Modified_Time is used as an approximation because no genuine close/audit "
    "timestamp is available for this module."
)


@dataclass(frozen=True)
class CloseTimestampResolution:
    timestamp: datetime | None
    status: CloseTimestampStatus
    disclosure: str | None


def resolve_close_timestamp(
    genuine_timestamp: datetime | None, modified_time: datetime | None
) -> CloseTimestampResolution:
    if genuine_timestamp is not None:
        return CloseTimestampResolution(
            genuine_timestamp, CloseTimestampStatus.VERIFIED_GENUINE, None
        )
    if modified_time is not None:
        return CloseTimestampResolution(
            modified_time,
            CloseTimestampStatus.APPROXIMATION_DISCLOSED,
            MODIFIED_TIME_DISCLOSURE,
        )
    return CloseTimestampResolution(None, CloseTimestampStatus.UNAVAILABLE, None)


def in_organization_timezone(instant: datetime, timezone_name: str) -> datetime:
    """Convert an aware instant without any browser/server fallback."""
    if instant.tzinfo is None:
        raise ValueError("An aware datetime is required")
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise TechnicalVerificationRequired(
            f"Unverified or unknown organization timezone: {timezone_name}"
        ) from error
    return instant.astimezone(timezone)

