"""Deterministic backtests for daily reference FX series such as H.10.

This module deliberately does not pretend a reference rate is executable bid/ask
market data. It evaluates simple directional hypotheses on the reference series
and reports gross/net forward returns with an explicit per-turn cost assumption.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Literal

from .h10_ingest import H10Observation


SignalRule = Literal["momentum", "reversal"]


@dataclass(frozen=True)
class ReferenceTrade:
    instrument: str
    decision_time: object
    signal: int
    entry_value: Decimal
    exit_value: Decimal
    gross_return: Decimal
    net_return: Decimal


def run_reference_backtest(
    observations: Iterable[H10Observation],
    *,
    instrument: str,
    rule: SignalRule,
    horizon: int = 1,
    one_way_cost_bps: Decimal = Decimal("0"),
) -> list[ReferenceTrade]:
    """Evaluate a fixed one-period directional rule on reference observations.

    The signal at t is based only on the change from the immediately preceding
    observation. The forward return is measured from t to t+horizon. Costs are
    applied as a round-trip percentage approximation (2 * one-way bps).
    """
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    if one_way_cost_bps < 0:
        raise ValueError("one_way_cost_bps cannot be negative")

    series = sorted(
        (x for x in observations if x.instrument == instrument),
        key=lambda x: (x.event_time, x.usable_at, x.observation_id),
    )
    trades: list[ReferenceTrade] = []
    round_trip_cost = (one_way_cost_bps * Decimal("2")) / Decimal("10000")

    for i in range(1, len(series) - horizon):
        current = series[i]
        previous = series[i - 1]
        if current.usable_at > current.event_time:
            continue
        if previous.usable_at > current.event_time:
            continue
        delta = current.value / previous.value - Decimal("1")
        signal = 0
        if delta > 0:
            signal = 1 if rule == "momentum" else -1
        elif delta < 0:
            signal = -1 if rule == "momentum" else 1
        if signal == 0:
            continue
        exit_obs = series[i + horizon]
        gross = signal * (exit_obs.value / current.value - Decimal("1"))
        net = gross - round_trip_cost
        trades.append(
            ReferenceTrade(
                instrument=instrument,
                decision_time=current.event_time,
                signal=signal,
                entry_value=current.value,
                exit_value=exit_obs.value,
                gross_return=gross,
                net_return=net,
            )
        )
    return trades


def summarize_reference_trades(trades: Iterable[ReferenceTrade]) -> dict[str, object]:
    """Return deterministic summary statistics without hiding empty samples."""
    rows = list(trades)
    if not rows:
        return {
            "n": 0,
            "mean_gross": None,
            "mean_net": None,
            "win_rate_net": None,
            "sum_net": None,
        }
    wins = sum(1 for row in rows if row.net_return > 0)
    mean_gross = sum((row.gross_return for row in rows), Decimal("0")) / Decimal(len(rows))
    mean_net = sum((row.net_return for row in rows), Decimal("0")) / Decimal(len(rows))
    sum_net = sum((row.net_return for row in rows), Decimal("0"))
    return {
        "n": len(rows),
        "mean_gross": mean_gross,
        "mean_net": mean_net,
        "win_rate_net": Decimal(wins) / Decimal(len(rows)),
        "sum_net": sum_net,
    }
