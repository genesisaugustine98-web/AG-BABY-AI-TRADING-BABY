"""Deterministic correlation-aware portfolio risk allocation primitives."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping


@dataclass(frozen=True)
class Exposure:
    instrument: str
    notional: Decimal
    volatility: Decimal
    beta: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if not self.instrument.strip() or not self.notional.is_finite() or self.volatility <= 0:
            raise ValueError("invalid exposure")
        if not self.beta.is_finite():
            raise ValueError("beta must be finite")


@dataclass(frozen=True)
class PortfolioRiskLimits:
    max_gross_notional_fraction: Decimal = Decimal("1")
    max_abs_net_notional_fraction: Decimal = Decimal("0.50")
    max_margin_fraction: Decimal = Decimal("0.50")
    max_portfolio_volatility: Decimal = Decimal("0.20")
    max_abs_beta_exposure: Decimal = Decimal("0.25")
    require_complete_correlation: bool = True
    conservative_unknown_correlation: Decimal = Decimal("0.75")

    def __post_init__(self) -> None:
        for name in (
            "max_gross_notional_fraction",
            "max_abs_net_notional_fraction",
            "max_margin_fraction",
            "max_portfolio_volatility",
            "max_abs_beta_exposure",
            "conservative_unknown_correlation",
        ):
            value = getattr(self, name)
            if not value.is_finite() or value < 0 or value > Decimal("1"):
                raise ValueError(f"{name} must be a finite fraction in [0,1]")


@dataclass(frozen=True)
class PortfolioRiskDecision:
    approved: bool
    reasons: tuple[str, ...]
    gross_fraction: Decimal
    net_fraction: Decimal
    margin_fraction: Decimal
    portfolio_volatility: Decimal
    beta_exposure: Decimal


class PortfolioRiskEngine:
    def __init__(self, limits: PortfolioRiskLimits | None = None) -> None:
        self.limits = limits or PortfolioRiskLimits()

    def _corr(self, a: str, b: str, matrix: Mapping[tuple[str, str], Decimal]) -> Decimal:
        if a == b:
            return Decimal("1")
        value = matrix.get((a, b), matrix.get((b, a)))
        if value is None:
            return self.limits.conservative_unknown_correlation
        return max(Decimal("-1"), min(Decimal("1"), Decimal(str(value))))

    def evaluate(
        self,
        *,
        exposures: tuple[Exposure, ...],
        account_equity: Decimal,
        margin_fraction: Decimal,
        correlation: Mapping[tuple[str, str], Decimal],
    ) -> PortfolioRiskDecision:
        if account_equity <= 0:
            raise ValueError("account_equity must be positive")
        if margin_fraction < 0:
            raise ValueError("margin_fraction must be non-negative")

        reasons: list[str] = []
        gross = sum(abs(x.notional) for x in exposures)
        net = sum(x.notional for x in exposures)
        weights = [x.notional / account_equity for x in exposures]

        variance = Decimal("0")
        for i, left in enumerate(exposures):
            for j, right in enumerate(exposures):
                if i < j and left.instrument != right.instrument and (left.instrument, right.instrument) not in correlation and (right.instrument, left.instrument) not in correlation:
                    if self.limits.require_complete_correlation:
                        reasons.append("PORTFOLIO_CORRELATION_INPUT_MISSING")
                corr = self._corr(left.instrument, right.instrument, correlation)
                variance += (
                    weights[i]
                    * weights[j]
                    * left.volatility
                    * right.volatility
                    * corr
                )
        portfolio_vol = max(Decimal("0"), variance).sqrt()
        beta = sum(
            (x.notional / account_equity) * x.beta for x in exposures
        )

        gross_fraction = gross / account_equity
        net_fraction = abs(net) / account_equity
        if gross_fraction > self.limits.max_gross_notional_fraction:
            reasons.append("PORTFOLIO_GROSS_NOTIONAL_LIMIT")
        if net_fraction > self.limits.max_abs_net_notional_fraction:
            reasons.append("PORTFOLIO_NET_NOTIONAL_LIMIT")
        if margin_fraction > self.limits.max_margin_fraction:
            reasons.append("PORTFOLIO_MARGIN_LIMIT")
        if portfolio_vol > self.limits.max_portfolio_volatility:
            reasons.append("PORTFOLIO_VOLATILITY_LIMIT")
        if abs(beta) > self.limits.max_abs_beta_exposure:
            reasons.append("PORTFOLIO_BETA_LIMIT")

        return PortfolioRiskDecision(
            not reasons,
            tuple(reasons),
            gross_fraction,
            net_fraction,
            margin_fraction,
            portfolio_vol,
            beta,
        )


__all__ = [
    "Exposure",
    "PortfolioRiskDecision",
    "PortfolioRiskEngine",
    "PortfolioRiskLimits",
]
