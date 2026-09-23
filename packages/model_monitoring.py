"""Online model-risk monitoring primitives.

These metrics are deliberately independent from the trading strategy. They provide an
institutional-style surveillance layer for feature distribution drift, probability quality,
and performance degradation. A deployment can choose to wire the resulting decision into
model governance without changing the execution kernel.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from math import log
from typing import Sequence


@dataclass(frozen=True)
class DriftDecision:
    allowed: bool
    psi: Decimal
    brier_score: Decimal | None
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class DriftLimits:
    max_psi: Decimal = Decimal("0.20")
    max_brier_score: Decimal = Decimal("0.25")

    def __post_init__(self) -> None:
        if not (Decimal("0") <= self.max_psi <= Decimal("10")):
            raise ValueError("max_psi must be between 0 and 10")
        if not (Decimal("0") <= self.max_brier_score <= Decimal("1")):
            raise ValueError("max_brier_score must be between 0 and 1")


def population_stability_index(expected: Sequence[Decimal], actual: Sequence[Decimal], *, epsilon: Decimal = Decimal("0.000001")) -> Decimal:
    if not expected or not actual or len(expected) != len(actual):
        raise ValueError("expected and actual distributions must have equal nonzero length")
    if epsilon <= 0:
        raise ValueError("epsilon must be positive")
    exp_total = sum((Decimal(str(x)) for x in expected), Decimal("0"))
    act_total = sum((Decimal(str(x)) for x in actual), Decimal("0"))
    if exp_total <= 0 or act_total <= 0:
        raise ValueError("distribution totals must be positive")
    psi = Decimal("0")
    for e, a in zip(expected, actual):
        ep = max(epsilon, Decimal(str(e)) / exp_total)
        ap = max(epsilon, Decimal(str(a)) / act_total)
        psi += (ap - ep) * Decimal(str(log(float(ap / ep))))
    return max(Decimal("0"), psi)


def brier_score(probabilities: Sequence[Decimal], outcomes: Sequence[int]) -> Decimal:
    if not probabilities or len(probabilities) != len(outcomes):
        raise ValueError("probabilities and outcomes must have equal nonzero length")
    total = Decimal("0")
    for probability, outcome in zip(probabilities, outcomes):
        p = Decimal(str(probability))
        if not (Decimal("0") <= p <= Decimal("1")):
            raise ValueError("probabilities must be in [0,1]")
        if outcome not in {0, 1}:
            raise ValueError("outcomes must be 0 or 1")
        total += (p - Decimal(outcome)) ** 2
    return total / Decimal(len(probabilities))


def evaluate_drift(
    *,
    expected_distribution: Sequence[Decimal],
    actual_distribution: Sequence[Decimal],
    probabilities: Sequence[Decimal] | None = None,
    outcomes: Sequence[int] | None = None,
    limits: DriftLimits | None = None,
) -> DriftDecision:
    policy = limits or DriftLimits()
    psi = population_stability_index(expected_distribution, actual_distribution)
    score = None
    reasons: list[str] = []
    if probabilities is not None or outcomes is not None:
        if probabilities is None or outcomes is None:
            raise ValueError("probabilities and outcomes must be supplied together")
        score = brier_score(probabilities, outcomes)
        if score > policy.max_brier_score:
            reasons.append("MODEL_BRIER_SCORE_LIMIT")
    if psi > policy.max_psi:
        reasons.append("FEATURE_DISTRIBUTION_PSI_LIMIT")
    return DriftDecision(not reasons, psi, score, tuple(reasons))


__all__ = [
    "DriftDecision",
    "DriftLimits",
    "brier_score",
    "evaluate_drift",
    "population_stability_index",
]
