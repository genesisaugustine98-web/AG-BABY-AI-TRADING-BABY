"""Evidence aggregation and deterministic research decision gate.

This module converts completed battery summaries into auditable evidence records.
It deliberately avoids declaring economic significance from arbitrary thresholds:
status is based on the predeclared evidence requirements supplied by the caller.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from statistics import median
from typing import Iterable


@dataclass(frozen=True)
class EvidenceStats:
    n: int
    mean_net: Decimal | None
    median_net: Decimal | None
    volatility: Decimal | None
    win_rate_net: Decimal | None
    cumulative_net: Decimal | None
    max_drawdown: Decimal | None
    breakeven_one_way_cost_bps: Decimal | None


def _drawdown(returns: list[Decimal]) -> Decimal | None:
    if not returns:
        return None
    equity = Decimal("1")
    peak = equity
    worst = Decimal("0")
    for value in returns:
        equity *= Decimal("1") + value
        peak = max(peak, equity)
        dd = equity / peak - Decimal("1")
        worst = min(worst, dd)
    return worst


def compute_stats(returns: Iterable[Decimal]) -> EvidenceStats:
    values = list(returns)
    if not values:
        return EvidenceStats(0, None, None, None, None, None, None, None)
    mean = sum(values, Decimal("0")) / Decimal(len(values))
    med = Decimal(str(median(values)))
    wins = sum(1 for x in values if x > 0)
    variance = sum((x - mean) ** 2 for x in values) / Decimal(len(values))
    vol = variance.sqrt()
    cumulative = Decimal("1")
    for x in values:
        cumulative *= Decimal("1") + x
    cumulative -= Decimal("1")
    return EvidenceStats(
        n=len(values),
        mean_net=mean,
        median_net=med,
        volatility=vol,
        win_rate_net=Decimal(wins) / Decimal(len(values)),
        cumulative_net=cumulative,
        max_drawdown=_drawdown(values),
        breakeven_one_way_cost_bps=None,
    )


def classify_evidence(
    *,
    stats: EvidenceStats,
    minimum_n: int,
    minimum_mean_net: Decimal,
    require_positive_cumulative: bool = True,
) -> str:
    """Classify without tuning: supported/not_supported/inconclusive."""
    if stats.n == 0 or stats.mean_net is None or stats.cumulative_net is None:
        return "inconclusive"
    if stats.n < minimum_n:
        return "inconclusive"
    if stats.mean_net < minimum_mean_net:
        return "not_supported"
    if require_positive_cumulative and stats.cumulative_net <= 0:
        return "not_supported"
    return "supported"


def cost_breakeven_mean_gross(mean_gross: Decimal) -> Decimal:
    """Return the maximum one-way bps compatible with non-negative mean net return."""
    # net = gross - 2 * one_way_bps / 10_000
    return max(Decimal("0"), mean_gross * Decimal("10000") / Decimal("2"))
