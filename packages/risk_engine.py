"""Deterministic pre-trade risk gate.

The risk engine is deliberately boring: explicit limits, exact Decimal arithmetic,
and a fail-closed decision. It never predicts prices and it never submits orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .models import AdmissionContext, InstrumentSpec, TradeIntent
from .risk import cash_risk_per_lot, volume_step_is_valid

D0 = Decimal("0")
ONE = Decimal("1")


def _fraction(value: Decimal | str | int | float, field: str) -> Decimal:
    value = value if isinstance(value, Decimal) else Decimal(str(value))
    if not value.is_finite() or value < D0 or value > ONE:
        raise ValueError(f"{field} must be a finite fraction in [0,1]")
    return value


@dataclass(frozen=True)
class RiskLimits:
    max_order_risk: Decimal = Decimal("0.01")
    max_strategy_risk: Decimal = Decimal("0.02")
    max_gross_risk: Decimal = Decimal("0.03")
    max_drawdown: Decimal = Decimal("0.08")
    max_daily_loss: Decimal = Decimal("0.03")
    max_open_positions: int = 8
    min_broker_health: Decimal = Decimal("0.80")
    min_data_health: Decimal = Decimal("0.80")

    def __post_init__(self) -> None:
        for name in ("max_order_risk", "max_strategy_risk", "max_gross_risk", "max_drawdown", "max_daily_loss", "min_broker_health", "min_data_health"):
            object.__setattr__(self, name, _fraction(getattr(self, name), name))
        if self.max_open_positions < 1:
            raise ValueError("max_open_positions must be >= 1")


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reasons: tuple[str, ...]
    requested_quantity: Decimal
    estimated_loss: Decimal
    order_risk_fraction: Decimal
    projected_gross_risk_fraction: Decimal


class DeterministicRiskEngine:
    def __init__(self, limits: RiskLimits | None = None):
        self.limits = limits or RiskLimits()

    def evaluate(self, *, intent: TradeIntent, context: AdmissionContext, instrument: InstrumentSpec) -> RiskDecision:
        reasons: list[str] = []
        quantity = Decimal(str(intent.quantity))
        side = intent.side.upper()
        equity = Decimal(str(context.portfolio.equity))

        if quantity <= 0:
            reasons.append("NON_POSITIVE_QUANTITY")
        if equity <= 0:
            reasons.append("INVALID_EQUITY")
        if side not in {"BUY", "SELL"}:
            reasons.append("INVALID_SIDE")
        if quantity < instrument.min_volume or quantity > instrument.max_volume:
            reasons.append("BROKER_VOLUME_BOUNDS")
        if not volume_step_is_valid(quantity, instrument.min_volume, instrument.max_volume, instrument.volume_step):
            reasons.append("BROKER_VOLUME_STEP")
        if context.portfolio.frozen:
            reasons.append("ACCOUNT_FROZEN")
        if context.market.broker_health < self.limits.min_broker_health:
            reasons.append("BROKER_HEALTH_BELOW_RISK_FLOOR")
        if context.market.data_health < self.limits.min_data_health:
            reasons.append("DATA_HEALTH_BELOW_RISK_FLOOR")
        if context.portfolio.account_drawdown_fraction > self.limits.max_drawdown:
            reasons.append("DRAWDOWN_LIMIT")
        if context.portfolio.daily_pnl < -(context.portfolio.equity * self.limits.max_daily_loss):
            reasons.append("DAILY_LOSS_LIMIT")
        if context.portfolio.open_positions >= self.limits.max_open_positions:
            reasons.append("OPEN_POSITION_LIMIT")

        stop_price = getattr(intent, "stop_price", None)
        if stop_price is None:
            reasons.append("STOP_REQUIRED")
            stop_distance = D0
        else:
            try:
                stop_distance = abs(context.quote.mid - Decimal(str(stop_price)))
            except (TypeError, ValueError):
                stop_distance = D0
                reasons.append("INVALID_STOP")

        try:
            loss_per_lot = cash_risk_per_lot(instrument, stop_distance)
        except ValueError:
            loss_per_lot = D0
            if "STOP_REQUIRED" not in reasons:
                reasons.append("INVALID_STOP_OR_TICK_SPEC")

        estimated_loss = max(D0, loss_per_lot * quantity)
        order_risk = estimated_loss / equity if equity > 0 else ONE
        projected_gross = context.portfolio.gross_risk_fraction + order_risk

        if order_risk > self.limits.max_order_risk:
            reasons.append("ORDER_RISK_LIMIT")
        if context.portfolio.strategy_risk_fraction + order_risk > self.limits.max_strategy_risk:
            reasons.append("STRATEGY_RISK_LIMIT")
        if projected_gross > self.limits.max_gross_risk:
            reasons.append("GROSS_RISK_LIMIT")
        if intent.risk_fraction > self.limits.max_order_risk:
            reasons.append("DECLARED_RISK_LIMIT")
        if stop_price is not None and side == "BUY" and Decimal(str(stop_price)) >= context.quote.mid:
            reasons.append("BUY_STOP_NOT_BELOW_MARKET")
        if stop_price is not None and side == "SELL" and Decimal(str(stop_price)) <= context.quote.mid:
            reasons.append("SELL_STOP_NOT_ABOVE_MARKET")

        return RiskDecision(
            approved=not reasons,
            reasons=tuple(dict.fromkeys(reasons)),
            requested_quantity=quantity,
            estimated_loss=estimated_loss,
            order_risk_fraction=order_risk,
            projected_gross_risk_fraction=projected_gross,
        )


__all__ = ["DeterministicRiskEngine", "RiskDecision", "RiskLimits"]
