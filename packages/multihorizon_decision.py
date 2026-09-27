"""Research-stage horizon consensus and selection.

This module intentionally returns a proposal only. It has no broker or capital access.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from statistics import pstdev

from .horizon import Timeframe


@dataclass(frozen=True)
class HorizonProposal:
    timeframe: Timeframe
    direction: int
    score: Decimal
    uncertainty: Decimal
    expected_hold_seconds: int
    reason_codes: tuple[str, ...]


def make_proposal(
    *,
    forecasts: dict[Timeframe, Decimal],
    expected_hold_seconds: int,
    execution_latency_seconds: int,
) -> HorizonProposal:
    if expected_hold_seconds < 1 or execution_latency_seconds < 0:
        raise ValueError("invalid holding/execution horizon")
    if not forecasts:
        raise ValueError("at least one forecast is required")
    clean = {tf: score for tf, score in forecasts.items() if score.is_finite()}
    if not clean:
        raise ValueError("forecasts contain no finite values")
    ordered = sorted(clean.items(), key=lambda x: (-abs(x[1]), x[0].value))
    primary_tf, primary_score = ordered[0]
    mean = sum(clean.values(), Decimal("0")) / Decimal(len(clean))
    dispersion = Decimal(str(pstdev(float(v) for v in clean.values()))) if len(clean) > 1 else Decimal("0")
    direction = 1 if mean > 0 else -1 if mean < 0 else 0
    reasons = ["MULTI_HORIZON_CONSENSUS"]
    if direction == 0:
        reasons.append("NO_DIRECTIONAL_CONSENSUS")
    if execution_latency_seconds >= expected_hold_seconds:
        reasons.append("EXECUTION_TOO_SLOW_FOR_HORIZON")
    if dispersion > Decimal("0.50"):
        reasons.append("HIGH_HORIZON_DISAGREEMENT")
    return HorizonProposal(
        timeframe=primary_tf,
        direction=direction,
        score=max(Decimal("-1"), min(Decimal("1"), mean)),
        uncertainty=max(Decimal("0"), min(Decimal("1"), dispersion)),
        expected_hold_seconds=expected_hold_seconds,
        reason_codes=tuple(reasons),
    )


__all__ = ["HorizonProposal", "make_proposal"]
