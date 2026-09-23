"""Evidence-gated model lifecycle governance.

The registry is deliberately stricter than a backtest score. Promotion is a state transition
based on explicit evidence; live promotion is permanently disabled in this repository.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from decimal import Decimal


class ModelState(str, Enum):
    CANDIDATE = "CANDIDATE"
    VALIDATED = "VALIDATED"
    SHADOW = "SHADOW"
    PAPER = "PAPER"
    DEMO = "DEMO"
    RETIRED = "RETIRED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class ModelEvidence:
    point_in_time: bool
    walk_forward: bool
    purged_validation: bool
    costs_modeled: bool
    slippage_modeled: bool
    multiple_testing_controlled: bool
    calibrated: bool
    stress_tested: bool
    calibration_score: Decimal
    max_drawdown_fraction: Decimal
    demo_validated: bool
    data_fingerprint: str
    code_commit_sha: str

    def complete_for_promotion(self, *, minimum_calibration_score: Decimal = Decimal("0.65")) -> bool:
        if not (Decimal("0") <= minimum_calibration_score <= Decimal("1")):
            raise ValueError("minimum_calibration_score must be in [0,1]")
        return all(
            (
                self.point_in_time,
                self.walk_forward,
                self.purged_validation,
                self.costs_modeled,
                self.slippage_modeled,
                self.multiple_testing_controlled,
                self.calibrated,
                self.stress_tested,
                self.demo_validated,
                self.calibration_score >= minimum_calibration_score,
                self.max_drawdown_fraction >= Decimal("0"),
                bool(self.data_fingerprint.strip()),
                bool(self.code_commit_sha.strip()),
            )
        )


@dataclass(frozen=True)
class PromotionDecision:
    allowed: bool
    target: ModelState
    reasons: tuple[str, ...]


_ALLOWED = {
    ModelState.CANDIDATE: {ModelState.VALIDATED, ModelState.REJECTED, ModelState.RETIRED},
    ModelState.VALIDATED: {ModelState.SHADOW, ModelState.PAPER, ModelState.RETIRED},
    ModelState.SHADOW: {ModelState.PAPER, ModelState.RETIRED},
    ModelState.PAPER: {ModelState.DEMO, ModelState.RETIRED},
    ModelState.DEMO: {ModelState.RETIRED},
    ModelState.RETIRED: set(),
    ModelState.REJECTED: {ModelState.RETIRED},
}


class ModelGovernance:
    def __init__(self, *, minimum_calibration_score: Decimal = Decimal("0.65"), maximum_promotable_drawdown: Decimal = Decimal("0.08")) -> None:
        if not (Decimal("0") <= minimum_calibration_score <= Decimal("1")):
            raise ValueError("minimum_calibration_score must be in [0,1]")
        if not (Decimal("0") <= maximum_promotable_drawdown <= Decimal("1")):
            raise ValueError("maximum_promotable_drawdown must be in [0,1]")
        self.minimum_calibration_score = minimum_calibration_score
        self.maximum_promotable_drawdown = maximum_promotable_drawdown

    def transition(
        self,
        *,
        current: ModelState,
        target: ModelState,
        evidence: ModelEvidence | None = None,
    ) -> PromotionDecision:
        reasons: list[str] = []
        if target == ModelState.DEMO and (evidence is None or not evidence.complete_for_promotion(minimum_calibration_score=self.minimum_calibration_score)):
            reasons.append("PROMOTION_EVIDENCE_INCOMPLETE")
        if evidence is not None and evidence.calibration_score < self.minimum_calibration_score:
            reasons.append("CALIBRATION_BELOW_PROMOTION_FLOOR")
        if evidence is not None and evidence.max_drawdown_fraction > self.maximum_promotable_drawdown:
            reasons.append("DRAWDOWN_ABOVE_PROMOTION_CEILING")
        if target in {ModelState.VALIDATED, ModelState.SHADOW, ModelState.PAPER, ModelState.DEMO}:
            if evidence is None:
                reasons.append("PROMOTION_EVIDENCE_REQUIRED")
        if target == ModelState.RETIRED:
            return PromotionDecision(True, target, ())
        if target not in _ALLOWED.get(current, set()):
            reasons.append(f"ILLEGAL_MODEL_TRANSITION:{current.value}->{target.value}")
        return PromotionDecision(not reasons, target, tuple(dict.fromkeys(reasons)))


__all__ = ["ModelEvidence", "ModelGovernance", "ModelState", "PromotionDecision"]
