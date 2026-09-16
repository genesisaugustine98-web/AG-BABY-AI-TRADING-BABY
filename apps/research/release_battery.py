"""Release-clock battery for causal H.10 reference-rate research.

A decision is made only from a release-time information state.  The forward target is
measured from the value available at that release to the value available at the next
selected release horizon.  No same-release future observation is allowed to leak into
the signal.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from .causal_panel import ReleaseState, assert_no_future_information, build_release_states


@dataclass(frozen=True)
class ReleaseTrade:
    instrument: str
    decision_time: object
    target_time: object
    signal: int
    entry_value: Decimal
    exit_value: Decimal
    gross_return: Decimal
    net_return: Decimal


def _signal(state: ReleaseState, rule: str) -> int:
    ret = state.prior_return
    if ret is None or ret == 0:
        return 0
    if rule == "momentum":
        return 1 if ret > 0 else -1
    if rule == "reversal":
        return -1 if ret > 0 else 1
    raise ValueError(f"unknown rule: {rule}")


def run_release_backtest(
    observations: Iterable,
    *,
    instrument: str,
    release_times: Iterable,
    rule: str,
    horizon_releases: int,
    one_way_cost_bps: Decimal = Decimal("0"),
) -> list[ReleaseTrade]:
    if horizon_releases < 1:
        raise ValueError("horizon_releases must be >= 1")
    if one_way_cost_bps < 0:
        raise ValueError("one_way_cost_bps cannot be negative")

    releases = sorted(release_times)
    states = build_release_states(
        observations,
        release_times=releases,
        instruments=[instrument],
    )
    assert_no_future_information(states)
    by_release = {state.release_at: state for state in states}
    series = [by_release[t] for t in releases]
    round_trip_cost = (one_way_cost_bps * Decimal("2")) / Decimal("10000")

    trades: list[ReleaseTrade] = []
    for i in range(len(series) - horizon_releases):
        state = series[i]
        target = series[i + horizon_releases]
        if state.latest_value is None or target.latest_value is None:
            continue
        signal = _signal(state, rule)
        if signal == 0:
            continue
        gross = signal * (target.latest_value / state.latest_value - Decimal("1"))
        net = gross - round_trip_cost
        trades.append(
            ReleaseTrade(
                instrument=instrument,
                decision_time=state.release_at,
                target_time=target.release_at,
                signal=signal,
                entry_value=state.latest_value,
                exit_value=target.latest_value,
                gross_return=gross,
                net_return=net,
            )
        )
    return trades


def summarize_release_trades(trades: Iterable[ReleaseTrade]) -> dict[str, object]:
    rows = list(trades)
    if not rows:
        return {"n": 0, "mean_gross": None, "mean_net": None, "win_rate_net": None, "sum_net": None}
    wins = sum(1 for row in rows if row.net_return > 0)
    total_net = sum((row.net_return for row in rows), Decimal("0"))
    total_gross = sum((row.gross_return for row in rows), Decimal("0"))
    return {
        "n": len(rows),
        "mean_gross": total_gross / Decimal(len(rows)),
        "mean_net": total_net / Decimal(len(rows)),
        "win_rate_net": Decimal(wins) / Decimal(len(rows)),
        "sum_net": total_net,
    }
