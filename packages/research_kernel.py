"""Deterministic research primitives: PIT observations and cost-aware replay."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Sequence


D0 = Decimal("0")


@dataclass(frozen=True)
class Observation:
    """A market observation with explicit event time and availability time."""

    symbol: str
    event_time_ms: int
    usable_at_ms: int
    mid: Decimal
    bid: Decimal
    ask: Decimal
    source: str
    source_version: str


@dataclass(frozen=True)
class QualityResult:
    accepted: bool
    reasons: tuple[str, ...]


def validate_observation(o: Observation) -> QualityResult:
    reasons: list[str] = []
    if not o.symbol:
        reasons.append("missing_symbol")
    if o.event_time_ms < 0 or o.usable_at_ms < 0:
        reasons.append("negative_timestamp")
    if o.usable_at_ms < o.event_time_ms:
        reasons.append("availability_before_event")
    if o.bid <= 0 or o.ask <= 0 or o.mid <= 0:
        reasons.append("non_positive_price")
    if o.ask < o.bid:
        reasons.append("crossed_quote")
    if o.source == "":
        reasons.append("missing_source")
    if o.source_version == "":
        reasons.append("missing_source_version")
    expected_mid = (o.bid + o.ask) / Decimal("2")
    if o.mid != expected_mid:
        reasons.append("mid_not_derived_from_quote")
    return QualityResult(not reasons, tuple(reasons))


def point_in_time(observations: Iterable[Observation], decision_time_ms: int) -> list[Observation]:
    """Return observations usable at decision_time in chronological order."""
    if decision_time_ms < 0:
        raise ValueError("decision_time_ms must be non-negative")
    selected = [o for o in observations if o.usable_at_ms <= decision_time_ms]
    return sorted(selected, key=lambda o: (o.event_time_ms, o.usable_at_ms, o.source))


@dataclass(frozen=True)
class ReplayBar:
    timestamp_ms: int
    mid: Decimal
    signal: int  # -1 short, 0 flat, +1 long


@dataclass(frozen=True)
class ReplayResult:
    total_return: Decimal
    gross_return: Decimal
    total_cost: Decimal
    turnover: Decimal
    trades: int
    observations: int


def cost_aware_replay(
    bars: Sequence[ReplayBar],
    *,
    spread_fraction: Decimal,
    slippage_fraction: Decimal,
    commission_fraction: Decimal,
    delay_bars: int = 0,
) -> ReplayResult:
    """Replay a position signal with explicit execution costs and delay.

    The position is marked to market between bars. Any residual position is
    explicitly flattened at the end of the sample so terminal exposure is not
    treated as free and turnover is fully accounted for.
    """
    if delay_bars < 0:
        raise ValueError("delay_bars must be non-negative")
    for value, name in (
        (spread_fraction, "spread_fraction"),
        (slippage_fraction, "slippage_fraction"),
        (commission_fraction, "commission_fraction"),
    ):
        if value < 0:
            raise ValueError(f"{name} must be non-negative")
    if not bars:
        return ReplayResult(D0, D0, D0, D0, 0, 0)

    for i in range(1, len(bars)):
        if bars[i].timestamp_ms <= bars[i - 1].timestamp_ms:
            raise ValueError("bars must have strictly increasing timestamps")
        if bars[i].mid <= 0:
            raise ValueError("mid must be positive")
        if bars[i].signal not in (-1, 0, 1):
            raise ValueError("signal must be -1, 0 or 1")
    if bars[0].mid <= 0:
        raise ValueError("mid must be positive")
    if bars[0].signal not in (-1, 0, 1):
        raise ValueError("signal must be -1, 0 or 1")

    position = 0
    gross = D0
    total_cost = D0
    turnover = D0
    trades = 0
    prev_mid = bars[0].mid
    execution_cost = spread_fraction / Decimal("2") + slippage_fraction + commission_fraction

    for i in range(1, len(bars)):
        desired_index = i - 1 - delay_bars
        desired = position if desired_index < 0 else bars[desired_index].signal
        if desired != position:
            change = Decimal(abs(desired - position))
            total_cost += change * execution_cost
            turnover += change
            trades += 1
            position = desired

        gross += Decimal(position) * ((bars[i].mid / prev_mid) - Decimal("1"))
        prev_mid = bars[i].mid

    if position != 0:
        change = Decimal(abs(position))
        total_cost += change * execution_cost
        turnover += change
        trades += 1

    return ReplayResult(gross - total_cost, gross, total_cost, turnover, trades, len(bars))
