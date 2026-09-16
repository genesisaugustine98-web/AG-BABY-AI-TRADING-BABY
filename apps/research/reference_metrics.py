"""Robust descriptive metrics for fixed-rule FX reference backtests."""
from __future__ import annotations

from decimal import Decimal, getcontext
from math import sqrt
from typing import Iterable

from .reference_backtest import ReferenceTrade

getcontext().prec = 40


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def _std(values: list[Decimal]) -> Decimal | None:
    if len(values) < 2:
        return None
    mean = _mean(values)
    assert mean is not None
    variance = sum((x - mean) ** 2 for x in values) / Decimal(len(values) - 1)
    return Decimal(str(sqrt(float(variance))))


def _max_drawdown(returns: list[Decimal]) -> Decimal | None:
    if not returns:
        return None
    equity = Decimal("1")
    peak = equity
    worst = Decimal("0")
    for ret in returns:
        equity *= Decimal("1") + ret
        peak = max(peak, equity)
        if peak > 0:
            drawdown = equity / peak - Decimal("1")
            worst = min(worst, drawdown)
    return worst


def summarize_detailed(trades: Iterable[ReferenceTrade]) -> dict[str, object]:
    rows = list(trades)
    if not rows:
        return {
            "n": 0,
            "mean_net": None,
            "std_net": None,
            "sharpe_like": None,
            "win_rate_net": None,
            "profit_factor": None,
            "max_drawdown": None,
            "gross_exposure": Decimal("0"),
            "net_sum": None,
        }

    net = [row.net_return for row in rows]
    wins = [x for x in net if x > 0]
    losses = [x for x in net if x < 0]
    mean_net = _mean(net)
    std_net = _std(net)
    sharpe_like = None
    if mean_net is not None and std_net not in (None, Decimal("0")):
        sharpe_like = mean_net / std_net * Decimal(str(sqrt(len(net))))
    profit_factor = None
    if losses:
        profit_factor = sum(wins, Decimal("0")) / abs(sum(losses, Decimal("0")))
    return {
        "n": len(rows),
        "mean_net": mean_net,
        "std_net": std_net,
        "sharpe_like": sharpe_like,
        "win_rate_net": Decimal(len(wins)) / Decimal(len(rows)),
        "profit_factor": profit_factor,
        "max_drawdown": _max_drawdown(net),
        "gross_exposure": Decimal(len(rows)),
        "net_sum": sum(net, Decimal("0")),
    }
