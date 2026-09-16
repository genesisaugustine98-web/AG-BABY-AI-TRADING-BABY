"""Canonical point-in-time panel helpers for reference FX observations."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Iterable

from .data_contract import MarketObservation


@dataclass(frozen=True)
class PanelPoint:
    instrument: str
    decision_time: datetime
    observation_time: datetime
    value: Decimal
    source_version: str
    observation_id: str


def latest_available(observations: Iterable[MarketObservation], *, instrument: str, decision_time: datetime) -> MarketObservation | None:
    """Return the latest observation whose usable_at is not after decision_time."""
    candidates = [x for x in observations if x.instrument == instrument and x.usable_for(decision_time)]
    if not candidates:
        return None
    return max(candidates, key=lambda x: (x.event_time, x.usable_at, x.observation_id))


def build_daily_panel(observations: Iterable[MarketObservation], *, decision_times: Iterable[datetime], instruments: Iterable[str]) -> list[PanelPoint]:
    """Build a deterministic long-form PIT panel."""
    source = list(observations)
    points: list[PanelPoint] = []
    for decision_time in sorted(decision_times):
        for instrument in sorted(set(instruments)):
            item = latest_available(source, instrument=instrument, decision_time=decision_time)
            if item is None:
                continue
            points.append(PanelPoint(item.instrument, decision_time, item.event_time, item.close, item.source_version, item.observation_id))
    return points
