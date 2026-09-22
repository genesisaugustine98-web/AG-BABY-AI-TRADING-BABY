"""Small dependency-free research validity primitives.

These are deliberately transparent gates rather than a black-box "strategy score".
They help quantify multiple-testing exposure and probability calibration without
turning a backtest result into an automatic production approval.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class MultipleTestingResult:
    alpha: Decimal
    p_values: tuple[Decimal, ...]
    rejected_indices: tuple[int, ...]
    threshold: Decimal | None


def benjamini_hochberg(p_values: list[Decimal | str | float], alpha: Decimal = Decimal("0.05")) -> MultipleTestingResult:
    """Benjamini-Hochberg false-discovery-rate control."""
    alpha = Decimal(str(alpha))
    if not (Decimal("0") < alpha <= Decimal("1")):
        raise ValueError("alpha must be in (0,1]")
    values = tuple(Decimal(str(p)) for p in p_values)
    if any(p < 0 or p > 1 for p in values):
        raise ValueError("p-values must be in [0,1]")
    ranked = sorted(enumerate(values), key=lambda pair: pair[1])
    passing = [(rank + 1, idx, p) for rank, (idx, p) in enumerate(ranked) if p <= alpha * Decimal(rank + 1) / Decimal(len(values) or 1)]
    if not passing:
        return MultipleTestingResult(alpha, values, (), None)
    max_rank = max(rank for rank, _, _ in passing)
    threshold = alpha * Decimal(max_rank) / Decimal(len(values))
    rejected = tuple(sorted(idx for idx, p in enumerate(values) if p <= threshold))
    return MultipleTestingResult(alpha, values, rejected, threshold)


def brier_score(probabilities: list[Decimal | str | float], outcomes: list[int]) -> Decimal:
    """Mean squared probability error for binary outcomes; lower is better descriptively."""
    if len(probabilities) != len(outcomes) or not probabilities:
        raise ValueError("probabilities and outcomes must have equal non-zero length")
    total = Decimal("0")
    for probability, outcome in zip(probabilities, outcomes):
        p = Decimal(str(probability))
        if not (Decimal("0") <= p <= Decimal("1")):
            raise ValueError("probability must be in [0,1]")
        if outcome not in (0, 1):
            raise ValueError("outcomes must be 0 or 1")
        total += (p - Decimal(outcome)) ** 2
    return total / Decimal(len(probabilities))


def expected_calibration_error(probabilities: list[Decimal | str | float], outcomes: list[int], bins: int = 10) -> Decimal:
    """Expected calibration error using equal-width probability bins."""
    if bins < 2:
        raise ValueError("bins must be >= 2")
    if len(probabilities) != len(outcomes) or not probabilities:
        raise ValueError("probabilities and outcomes must have equal non-zero length")
    grouped: list[list[tuple[Decimal, int]]] = [[] for _ in range(bins)]
    for probability, outcome in zip(probabilities, outcomes):
        p = Decimal(str(probability))
        if not (Decimal("0") <= p <= Decimal("1")) or outcome not in (0, 1):
            raise ValueError("invalid calibration input")
        index = min(bins - 1, int(p * bins))
        grouped[index].append((p, outcome))
    total = Decimal("0")
    n = Decimal(len(probabilities))
    for bucket in grouped:
        if not bucket:
            continue
        avg_p = sum((p for p, _ in bucket), Decimal("0")) / Decimal(len(bucket))
        avg_y = Decimal(sum(y for _, y in bucket)) / Decimal(len(bucket))
        total += Decimal(len(bucket)) / n * abs(avg_p - avg_y)
    return total


def max_drawdown(returns: list[Decimal | str | float]) -> Decimal:
    """Maximum peak-to-trough drawdown on cumulative simple-return wealth."""
    wealth = Decimal("1")
    peak = wealth
    worst = Decimal("0")
    for raw in returns:
        r = Decimal(str(raw))
        if not r.is_finite() or r <= Decimal("-1"):
            raise ValueError("returns must be finite and greater than -1")
        wealth *= Decimal("1") + r
        peak = max(peak, wealth)
        if peak > 0:
            worst = max(worst, (peak - wealth) / peak)
    return worst


__all__ = ["MultipleTestingResult", "benjamini_hochberg", "brier_score", "expected_calibration_error", "max_drawdown"]
