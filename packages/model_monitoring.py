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
from typing import Sequence, Any


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


@dataclass(frozen=True)
class SurveillanceLimits:
    max_psi: Decimal = Decimal("0.20")
    max_brier_score: Decimal = Decimal("0.25")
    min_rolling_net_bps: Decimal | None = None
    max_drawdown_fraction: Decimal = Decimal("0.08")
    max_consecutive_breaches: int = 3

    def __post_init__(self) -> None:
        if not (Decimal("0") <= self.max_psi <= Decimal("10")): raise ValueError("max_psi must be between 0 and 10")
        if not (Decimal("0") <= self.max_brier_score <= Decimal("1")): raise ValueError("max_brier_score must be between 0 and 1")
        if self.min_rolling_net_bps is not None and not self.min_rolling_net_bps.is_finite(): raise ValueError("min_rolling_net_bps must be finite")
        if not (Decimal("0") <= self.max_drawdown_fraction <= Decimal("1")): raise ValueError("max_drawdown_fraction must be between 0 and 1")
        if self.max_consecutive_breaches < 1: raise ValueError("max_consecutive_breaches must be >= 1")


@dataclass(frozen=True)
class ModelSurveillanceState:
    model_id: str
    version: str
    consecutive_breaches: int
    last_decision: str = "RETAIN"


@dataclass(frozen=True)
class ModelSurveillanceDecision:
    decision: str
    breach_count: int
    reasons: tuple[str, ...]
    psi: Decimal | None
    brier_score: Decimal | None
    rolling_net_bps: Decimal | None
    drawdown_fraction: Decimal | None


class ModelSurveillanceEngine:
    def __init__(self, *, limits: SurveillanceLimits | None = None) -> None:
        self.limits = limits or SurveillanceLimits()
        self._state: dict[tuple[str, str], ModelSurveillanceState] = {}

    def observe(
        self,
        *,
        model_id: str,
        version: str,
        psi: Decimal | None = None,
        brier_score_value: Decimal | None = None,
        rolling_net_bps: Decimal | None = None,
        drawdown_fraction: Decimal | None = None,
    ) -> ModelSurveillanceDecision:
        model_key = (str(model_id).strip(), str(version).strip())
        if not model_key[0] or not model_key[1]: raise ValueError("model identity is required")
        reasons: list[str] = []
        for value, lower, upper, label in (
            (psi, Decimal("0"), self.limits.max_psi, "FEATURE_DISTRIBUTION_PSI_LIMIT"),
            (brier_score_value, Decimal("0"), self.limits.max_brier_score, "MODEL_BRIER_SCORE_LIMIT"),
            (drawdown_fraction, Decimal("0"), self.limits.max_drawdown_fraction, "MODEL_DRAWDOWN_LIMIT"),
        ):
            if value is not None:
                value = Decimal(str(value))
                if not value.is_finite() or value < lower: raise ValueError(f"invalid surveillance metric:{label}")
                if value > upper: reasons.append(label)
        if rolling_net_bps is not None:
            rolling_net_bps = Decimal(str(rolling_net_bps))
            if not rolling_net_bps.is_finite(): raise ValueError("rolling_net_bps must be finite")
            if self.limits.min_rolling_net_bps is not None and rolling_net_bps < self.limits.min_rolling_net_bps:
                reasons.append("ROLLING_NET_PERFORMANCE_FLOOR")
        previous=self._state.get(model_key, ModelSurveillanceState(model_key[0],model_key[1],0))
        breaches = previous.consecutive_breaches + 1 if reasons else 0
        decision = "RETIRE" if breaches >= self.limits.max_consecutive_breaches else "RETAIN"
        current=ModelSurveillanceState(model_key[0],model_key[1],breaches,decision)
        self._state[model_key]=current
        return ModelSurveillanceDecision(decision,breaches,tuple(dict.fromkeys(reasons)),None if psi is None else Decimal(str(psi)),
            None if brier_score_value is None else Decimal(str(brier_score_value)),
            None if rolling_net_bps is None else Decimal(str(rolling_net_bps)),
            None if drawdown_fraction is None else Decimal(str(drawdown_fraction)))

    def seed_state(self, *, model_id: str, version: str, consecutive_breaches: int, last_decision: str = "RETAIN") -> None:
        model_id = str(model_id).strip(); version = str(version).strip()
        if not model_id or not version or consecutive_breaches < 0:
            raise ValueError("invalid surveillance seed")
        self._state[(model_id, version)] = ModelSurveillanceState(model_id, version, int(consecutive_breaches), last_decision)

    def state(self, *, model_id: str, version: str) -> ModelSurveillanceState:
        key=(str(model_id).strip(),str(version).strip())
        return self._state.get(key, ModelSurveillanceState(key[0],key[1],0))



__all__ = [
    "DriftDecision",
    "DriftLimits",
    "brier_score",
    "evaluate_drift",
    "population_stability_index",
    "ModelSurveillanceDecision",
    "ModelSurveillanceEngine",
    "ModelSurveillanceState",
    "SurveillanceLimits",
]
