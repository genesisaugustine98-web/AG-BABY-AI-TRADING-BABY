"""Deterministic multi-strategy candidate allocation.

Allocation happens before order construction. It does not optimize on hidden outcomes; the
caller provides an explicit strategy order and risk budget.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from packages.opportunity import OpportunityCandidate


@dataclass(frozen=True)
class AllocationLimits:
    max_total_risk: Decimal = Decimal("0.03")
    max_per_strategy_risk: Decimal = Decimal("0.02")
    max_per_instrument_risk: Decimal = Decimal("0.01")
    max_candidates: int = 8

    def __post_init__(self) -> None:
        for value in (self.max_total_risk, self.max_per_strategy_risk, self.max_per_instrument_risk):
            if value < 0 or value > Decimal("1"):
                raise ValueError("risk limits must be fractions in [0,1]")
        if self.max_candidates < 1:
            raise ValueError("max_candidates must be >= 1")


@dataclass(frozen=True)
class AllocationResult:
    approved: tuple[OpportunityCandidate, ...]
    rejected: tuple[tuple[str, str], ...]
    total_risk: Decimal


class StrategyAllocator:
    def __init__(self, limits: AllocationLimits | None = None) -> None:
        self.limits = limits or AllocationLimits()

    def allocate(
        self,
        *,
        candidates: tuple[OpportunityCandidate, ...],
        strategy_order: tuple[str, ...],
    ) -> AllocationResult:
        order_index = {strategy_id: index for index, strategy_id in enumerate(strategy_order)}
        ordered = sorted(
            (candidate for candidate in candidates if candidate.state == "ADMITTED"),
            key=lambda c: (order_index.get(c.model_id, len(order_index)), c.candidate_id),
        )
        approved: list[OpportunityCandidate] = []
        rejected: list[tuple[str, str]] = []
        strategy_risk: dict[str, Decimal] = {}
        instrument_risk: dict[str, Decimal] = {}
        total = Decimal("0")

        for candidate in ordered:
            risk = candidate.suggested_risk
            strategy_key = candidate.model_id
            instrument_key = candidate.instrument
            reason = None
            if len(approved) >= self.limits.max_candidates:
                reason = "MAX_CANDIDATES"
            elif total + risk > self.limits.max_total_risk:
                reason = "TOTAL_RISK_LIMIT"
            elif strategy_risk.get(strategy_key, Decimal("0")) + risk > self.limits.max_per_strategy_risk:
                reason = "STRATEGY_RISK_LIMIT"
            elif instrument_risk.get(instrument_key, Decimal("0")) + risk > self.limits.max_per_instrument_risk:
                reason = "INSTRUMENT_RISK_LIMIT"
            if reason:
                rejected.append((candidate.candidate_id, reason))
                continue
            approved.append(candidate)
            total += risk
            strategy_risk[strategy_key] = strategy_risk.get(strategy_key, Decimal("0")) + risk
            instrument_risk[instrument_key] = instrument_risk.get(instrument_key, Decimal("0")) + risk

        return AllocationResult(tuple(approved), tuple(rejected), total)


__all__ = ["AllocationLimits", "AllocationResult", "StrategyAllocator"]
