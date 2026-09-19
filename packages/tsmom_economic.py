"""Cost-aware economic validation for the fixed TSMOM model.

The model is fit only on the development split. Validation and holdout returns are
then replayed with the frozen model. Cost assumptions are explicit sensitivity inputs,
not historical execution measurements. This module never submits broker orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from math import sqrt
from typing import Iterable, Sequence

from .tsmom_forecast import PriceBar, TSMOMForecastModel

D0 = Decimal("0")
D1 = Decimal("1")


@dataclass(frozen=True)
class EconomicResult:
    split: str
    n: int
    sample_start: int | None
    sample_end: int | None
    assumed_one_way_cost_bps: Decimal
    delay_bars: int
    horizon_bars: int
    mean_gross: Decimal | None
    mean_net: Decimal | None
    cumulative_net: Decimal | None
    max_drawdown: Decimal | None
    win_rate_net: Decimal | None
    profit_factor: Decimal | None
    sharpe_like: Decimal | None
    breakeven_one_way_cost_bps: Decimal | None


def _max_drawdown(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    wealth = D1
    peak = D1
    worst = D0
    for value in values:
        wealth *= D1 + value
        peak = max(peak, wealth)
        worst = min(worst, wealth / peak - D1)
    return abs(worst)


def _summarize(
    *,
    split: str,
    rows: list[tuple[int, Decimal, Decimal]],
    cost_bps: Decimal,
    delay_bars: int,
    horizon_bars: int,
) -> EconomicResult:
    if not rows:
        return EconomicResult(
            split, 0, None, None, cost_bps, delay_bars, horizon_bars,
            None, None, None, None, None, None, None, None
        )
    gross = [row[1] for row in rows]
    net = [row[2] for row in rows]
    mean_gross = sum(gross, D0) / Decimal(len(gross))
    mean_net = sum(net, D0) / Decimal(len(net))
    cumulative = D1
    for value in net:
        cumulative *= D1 + value
    cumulative -= D1
    wins = sum(1 for value in net if value > D0)
    losses = sum(1 for value in net if value < D0)
    profit_factor = (
        sum((value for value in net if value > D0), D0)
        / abs(sum((value for value in net if value < D0), D0))
        if losses else None
    )
    variance = sum((value - mean_net) ** 2 for value in net) / Decimal(len(net) - 1) if len(net) > 1 else D0
    std = variance.sqrt() if variance > D0 else D0
    sharpe_like = mean_net / std * Decimal(str(sqrt(len(net)))) if std > D0 else None
    breakeven = max(D0, mean_gross * Decimal("10000") / Decimal("2"))
    return EconomicResult(
        split, len(rows), rows[0][0], rows[-1][0], cost_bps, delay_bars, horizon_bars,
        mean_gross, mean_net, cumulative, _max_drawdown(net),
        Decimal(wins) / Decimal(len(net)), profit_factor, sharpe_like, breakeven
    )


def evaluate_split(
    model: TSMOMForecastModel,
    bars: Iterable[PriceBar],
    *,
    split: str,
    start_index: int,
    end_index: int,
    one_way_cost_bps: Decimal,
    delay_bars: int = 0,
) -> EconomicResult:
    """Evaluate a frozen model inside one chronological split only."""
    rows = sorted(list(bars), key=lambda x: (x.event_time_ms, x.usable_at_ms, x.observation_id))
    if start_index < 0 or end_index <= start_index or end_index > len(rows):
        raise ValueError("invalid split bounds")
    if one_way_cost_bps < D0:
        raise ValueError("one_way_cost_bps cannot be negative")
    if delay_bars < 0:
        raise ValueError("delay_bars cannot be negative")

    round_trip_cost = Decimal("2") * one_way_cost_bps / Decimal("10000")
    trades: list[tuple[int, Decimal, Decimal]] = []
    first = max(start_index, model.lookback_bars)
    last = min(
        end_index - 1 - delay_bars - model.horizon_bars,
        len(rows) - 1 - delay_bars - model.horizon_bars,
    )
    for i in range(first, last + 1):
        decision = rows[i]
        forecast = model.predict(rows, decision_time_ms=decision.event_time_ms)
        entry = rows[i + delay_bars]
        exit_bar = rows[i + delay_bars + model.horizon_bars]
        gross = forecast.expected_return * (D1 if forecast.expected_return >= D0 else -D1)
        # Economic replay uses the model's realized directional signal, not its forecast magnitude.
        signal = D1 if forecast.expected_return > D0 else -D1
        realized = signal * (exit_bar.close / entry.close - D1)
        net = realized - round_trip_cost
        trades.append((decision.event_time_ms, realized, net))
    return _summarize(
        split=split,
        rows=trades,
        cost_bps=one_way_cost_bps,
        delay_bars=delay_bars,
        horizon_bars=model.horizon_bars,
    )


def chronological_split_indices(
    n: int,
    *,
    development_fraction: Decimal = Decimal("0.60"),
    validation_fraction: Decimal = Decimal("0.20"),
) -> dict[str, tuple[int, int]]:
    if n < 3:
        raise ValueError("at least three observations are required")
    holdout_fraction = D1 - development_fraction - validation_fraction
    if min(development_fraction, validation_fraction, holdout_fraction) <= D0:
        raise ValueError("split fractions must all be positive")
    dev_end = int(n * development_fraction)
    val_end = dev_end + int(n * validation_fraction)
    if dev_end <= 0 or val_end <= dev_end or val_end >= n:
        raise ValueError("fractions produce invalid splits")
    return {
        "development": (0, dev_end),
        "validation": (dev_end, val_end),
        "holdout": (val_end, n),
    }


__all__ = ["EconomicResult", "chronological_split_indices", "evaluate_split"]
