"""Structural research-evidence gate for model promotion.

This gate does not decide whether a strategy is profitable. It verifies that the supplied research
package contains enough independent/out-of-sample and friction-stress structure to be considered
promotion evidence at all.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Any


@dataclass(frozen=True)
class ResearchPromotionRequirements:
    min_independent_validation_periods: int = 3
    min_cost_stress_points: int = 2
    min_slippage_stress_points: int = 2
    require_untouched_holdout: bool = True
    require_regime_coverage: bool = True
    require_selection_lock: bool = True

    def __post_init__(self) -> None:
        if self.min_independent_validation_periods < 1:
            raise ValueError("min_independent_validation_periods must be >= 1")
        if self.min_cost_stress_points < 1 or self.min_slippage_stress_points < 1:
            raise ValueError("stress requirements must be >= 1")


@dataclass(frozen=True)
class ResearchPromotionDecision:
    allowed: bool
    reasons: tuple[str, ...]


def evaluate_research_package(
    evidence: Mapping[str, Any],
    *,
    requirements: ResearchPromotionRequirements | None = None,
) -> ResearchPromotionDecision:
    req = requirements or ResearchPromotionRequirements()
    reasons: list[str] = []

    validation_periods = int(evidence.get("independent_validation_periods", 0))
    cost_stress = int(evidence.get("cost_stress_points", 0))
    slippage_stress = int(evidence.get("slippage_stress_points", 0))

    if validation_periods < req.min_independent_validation_periods:
        reasons.append("INSUFFICIENT_INDEPENDENT_VALIDATION_PERIODS")
    if cost_stress < req.min_cost_stress_points:
        reasons.append("INSUFFICIENT_COST_STRESS_POINTS")
    if slippage_stress < req.min_slippage_stress_points:
        reasons.append("INSUFFICIENT_SLIPPAGE_STRESS_POINTS")
    if req.require_untouched_holdout and not bool(evidence.get("untouched_holdout", False)):
        reasons.append("UNTOUCHED_HOLDOUT_REQUIRED")
    if req.require_regime_coverage and not bool(evidence.get("regime_coverage", False)):
        reasons.append("REGIME_COVERAGE_REQUIRED")
    if req.require_selection_lock and not bool(evidence.get("selection_lock", False)):
        reasons.append("SELECTION_LOCK_REQUIRED")
    for field in ("research_run_id", "research_commit_sha", "evaluation_dataset_fingerprint"):
        if not str(evidence.get(field) or "").strip():
            reasons.append(f"RESEARCH_LINEAGE_MISSING:{field}")

    return ResearchPromotionDecision(not reasons, tuple(dict.fromkeys(reasons)))


__all__ = [
    "ResearchPromotionDecision",
    "ResearchPromotionRequirements",
    "evaluate_research_package",
]
