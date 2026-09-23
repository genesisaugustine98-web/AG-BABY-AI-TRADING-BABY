"""Institutional-style correlation-aware candidate allocation.

This module operates on *risk-budget fractions*, not raw currency notionals. It is therefore
appropriate at the strategy-allocation boundary where exact broker valuation may not yet be
available. The rule is deliberately conservative: existing committed risk consumes budget
first, and missing cross-instrument correlations are either explicitly rejected or replaced by
a documented conservative floor.

It is deterministic and contains no forecasting or broker submission logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from math import isfinite
from typing import Mapping

from .opportunity import OpportunityCandidate
from .strategy_allocator import AllocationLimits, AllocationResult


@dataclass(frozen=True)
class InstitutionalAllocationLimits:
    max_total_risk: Decimal = Decimal("0.03")
    max_per_strategy_risk: Decimal = Decimal("0.02")
    max_per_instrument_risk: Decimal = Decimal("0.01")
    max_candidates: int = 8
    max_correlation_adjusted_risk: Decimal = Decimal("0.03")
    max_abs_net_risk: Decimal = Decimal("0.03")
    require_complete_correlations: bool = True
    conservative_unknown_correlation: Decimal = Decimal("0.75")

    def __post_init__(self) -> None:
        for name in (
            "max_total_risk",
            "max_per_strategy_risk",
            "max_per_instrument_risk",
            "max_correlation_adjusted_risk",
            "max_abs_net_risk",
            "conservative_unknown_correlation",
        ):
            value = getattr(self, name)
            if not value.is_finite() or value < 0 or value > Decimal("1"):
                raise ValueError(f"{name} must be a finite fraction in [0,1]")
        if self.max_candidates < 1:
            raise ValueError("max_candidates must be >= 1")


class InstitutionalStrategyAllocator:
    """Base deterministic allocator plus correlation/concentration admission."""

    def __init__(
        self,
        limits: InstitutionalAllocationLimits | None = None,
        *,
        correlations: Mapping[tuple[str, str], Decimal] | None = None,
        current_risk_provider=None,
    ) -> None:
        self.limits = limits or InstitutionalAllocationLimits()
        self.correlations = dict(correlations or {})
        self.current_risk_provider = current_risk_provider

    def _current_risk(self) -> Decimal:
        if self.current_risk_provider is None:
            return Decimal("0")
        value = Decimal(str(self.current_risk_provider()))
        if not value.is_finite() or value < 0 or value > Decimal("1"):
            raise RuntimeError("current portfolio risk provider returned an invalid fraction")
        return value

    def _correlation(self, left: str, right: str) -> tuple[Decimal, bool]:
        if left == right:
            return Decimal("1"), True
        raw = self.correlations.get((left, right))
        if raw is None:
            raw = self.correlations.get((right, left))
        if raw is None:
            return self.limits.conservative_unknown_correlation, False
        value = Decimal(str(raw))
        if not value.is_finite() or value < Decimal("-1") or value > Decimal("1"):
            raise ValueError(f"invalid portfolio correlation:{left}:{right}")
        return value, True

    def _portfolio_score(self, candidates: list[OpportunityCandidate]) -> tuple[Decimal, bool]:
        if not candidates:
            return Decimal("0"), True
        variance = Decimal("0")
        complete = True
        weights = [candidate.suggested_risk for candidate in candidates]
        for i, left in enumerate(candidates):
            for j, right in enumerate(candidates):
                corr, known = self._correlation(left.instrument, right.instrument)
                complete = complete and known
                variance += weights[i] * weights[j] * corr
        return max(Decimal("0"), variance).sqrt(), complete

    @staticmethod
    def _signed(candidate: OpportunityCandidate) -> Decimal:
        if candidate.side.upper() == "BUY":
            return candidate.suggested_risk
        if candidate.side.upper() == "SELL":
            return -candidate.suggested_risk
        raise ValueError(f"unsupported candidate side:{candidate.side}")

    def allocate(
        self,
        *,
        candidates: tuple[OpportunityCandidate, ...],
        strategy_order: tuple[str, ...],
    ) -> AllocationResult:
        order_index = {strategy_id: index for index, strategy_id in enumerate(strategy_order)}
        ordered = sorted(
            (candidate for candidate in candidates if candidate.state == "ADMITTED"),
            key=lambda candidate: (
                order_index.get(candidate.strategy_id, len(order_index)),
                candidate.candidate_id,
            ),
        )

        approved: list[OpportunityCandidate] = []
        rejected: list[tuple[str, str]] = []
        strategy_risk: dict[str, Decimal] = {}
        instrument_risk: dict[str, Decimal] = {}
        total = Decimal("0")

        for candidate in ordered:
            risk = candidate.suggested_risk
            if not risk.is_finite() or risk <= 0:
                rejected.append((candidate.candidate_id, "INVALID_CANDIDATE_RISK"))
                continue

            strategy_key = candidate.strategy_id
            instrument_key = candidate.instrument
            reason: str | None = None

            if len(approved) >= self.limits.max_candidates:
                reason = "MAX_CANDIDATES"
            elif total + self._current_risk() + risk > self.limits.max_total_risk:
                reason = "TOTAL_RISK_LIMIT"
            elif strategy_risk.get(strategy_key, Decimal("0")) + risk > self.limits.max_per_strategy_risk:
                reason = "STRATEGY_RISK_LIMIT"
            elif instrument_risk.get(instrument_key, Decimal("0")) + risk > self.limits.max_per_instrument_risk:
                reason = "INSTRUMENT_RISK_LIMIT"
            else:
                trial = approved + [candidate]
                portfolio_score, complete = self._portfolio_score(trial)
                adjusted = self._current_risk() + portfolio_score
                signed_net = abs(sum((self._signed(item) for item in trial), Decimal("0")))
                if self.limits.require_complete_correlations and not complete:
                    reason = "PORTFOLIO_CORRELATION_DATA_INCOMPLETE"
                elif adjusted > self.limits.max_correlation_adjusted_risk:
                    reason = "PORTFOLIO_CORRELATION_RISK_LIMIT"
                elif self._current_risk() + signed_net > self.limits.max_abs_net_risk:
                    reason = "PORTFOLIO_NET_RISK_LIMIT"

            if reason:
                rejected.append((candidate.candidate_id, reason))
                continue

            approved.append(candidate)
            total += risk
            strategy_risk[strategy_key] = strategy_risk.get(strategy_key, Decimal("0")) + risk
            instrument_risk[instrument_key] = instrument_risk.get(instrument_key, Decimal("0")) + risk

        return AllocationResult(tuple(approved), tuple(rejected), total)


def correlations_from_env_payload(payload: str) -> dict[tuple[str, str], Decimal]:
    """Parse {"EURUSD,GBPUSD": "0.78", "EURUSD:USDJPY": 0.55} deterministically."""
    import json

    raw = payload.strip()
    if not raw:
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("AG_PORTFOLIO_CORRELATIONS must be a JSON object")
    result: dict[tuple[str, str], Decimal] = {}
    for key, value in parsed.items():
        delimiter = "," if "," in str(key) else ":"
        parts = [part.strip().upper() for part in str(key).split(delimiter)]
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(f"invalid correlation key:{key}")
        result[(parts[0], parts[1])] = Decimal(str(value))
    return result

def betas_from_env_payload(payload: str) -> dict[str, Decimal]:
    """Parse {"EURUSD": 0.10, "USDJPY": -0.05} into normalized instrument betas."""
    import json

    raw = payload.strip()
    if not raw:
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("AG_PORTFOLIO_BETAS must be a JSON object")
    result: dict[str, Decimal] = {}
    for key, value in parsed.items():
        instrument = str(key).strip().upper()
        beta = Decimal(str(value))
        if not instrument or not beta.is_finite():
            raise ValueError(f"invalid portfolio beta:{key}")
        result[instrument] = beta
    return result


__all__ = [
    "InstitutionalAllocationLimits",
    "InstitutionalStrategyAllocator",
    "correlations_from_env_payload",
    "betas_from_env_payload",
]
