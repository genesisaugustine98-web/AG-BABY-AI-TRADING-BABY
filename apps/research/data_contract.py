"""Point-in-time market-data contracts and validation primitives.

Rules:
- event_time is when the observation occurred;
- usable_at is the earliest time the observation may be used by research;
- no observation with usable_at > decision_time may influence a decision;
- provenance and revision/vintage identifiers are mandatory for reproducibility.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal


@dataclass(frozen=True)
class MarketObservation:
    instrument: str
    event_time: datetime
    usable_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    source: str
    source_version: str
    observation_id: str

    def __post_init__(self) -> None:
        for name in ("event_time", "usable_at"):
            value = getattr(self, name)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high is inconsistent with OHLC values")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low is inconsistent with OHLC values")
        if any(value <= 0 for value in (self.open, self.high, self.low, self.close)):
            raise ValueError("FX prices must be positive")
        if not self.source or not self.source_version or not self.observation_id:
            raise ValueError("source, source_version and observation_id are required")

    def usable_for(self, decision_time: datetime) -> bool:
        if decision_time.tzinfo is None or decision_time.utcoffset() is None:
            raise ValueError("decision_time must be timezone-aware")
        return self.usable_at <= decision_time


def utc_from_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def filter_point_in_time(
    observations: list[MarketObservation], decision_time: datetime
) -> list[MarketObservation]:
    """Return only observations legally available by decision_time."""
    return [item for item in observations if item.usable_for(decision_time)]
