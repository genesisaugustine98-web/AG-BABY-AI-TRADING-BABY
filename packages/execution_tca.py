"""Execution transaction-cost analysis (TCA) primitives.

TCA is an observation layer over confirmed broker fills. It never authorizes an order and
never mutates accounting. Slippage is signed from the trading decision's perspective.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping

_BPS = Decimal("10000")

def signed_slippage_fraction(*, side: str, decision_mid: Decimal, execution_price: Decimal) -> Decimal:
    side = side.strip().upper()
    decision_mid = Decimal(str(decision_mid)); execution_price = Decimal(str(execution_price))
    if side not in {"BUY", "SELL"}: raise ValueError("side must be BUY or SELL")
    if decision_mid <= 0 or execution_price <= 0: raise ValueError("decision_mid and execution_price must be positive")
    return ((execution_price - decision_mid) / decision_mid) if side == "BUY" else ((decision_mid - execution_price) / decision_mid)

@dataclass(frozen=True)
class TCAObservation:
    environment: str
    observed_at: str
    order_id: str
    broker_order_id: str | None
    strategy_id: str
    model_id: str
    model_version: str
    instrument: str
    side: str
    requested_quantity: Decimal
    filled_quantity: Decimal
    decision_mid: Decimal
    execution_price: Decimal
    arrival_spread: Decimal
    slippage_fraction: Decimal
    slippage_bps: Decimal
    spread_bps: Decimal
    commission: Decimal
    financing: Decimal
    total_cost_fraction: Decimal
    implementation_shortfall_quote: Decimal
    metadata: Mapping[str, Any]

    @classmethod
    def from_fill(cls, *, environment: str, order_id: str, broker_order_id: str | None,
                  strategy_id: str, model_id: str, model_version: str, instrument: str, side: str,
                  requested_quantity: Decimal, filled_quantity: Decimal, decision_mid: Decimal,
                  execution_price: Decimal, arrival_spread: Decimal, commission: Decimal,
                  financing: Decimal, observed_at: str, metadata: Mapping[str, Any] | None = None) -> "TCAObservation":
        requested_quantity = Decimal(str(requested_quantity)); filled_quantity = Decimal(str(filled_quantity))
        decision_mid = Decimal(str(decision_mid)); execution_price = Decimal(str(execution_price))
        arrival_spread = Decimal(str(arrival_spread)); commission = Decimal(str(commission)); financing = Decimal(str(financing))
        if requested_quantity <= 0 or filled_quantity <= 0 or filled_quantity > requested_quantity: raise ValueError("invalid TCA quantities")
        if arrival_spread < 0 or commission < 0: raise ValueError("arrival spread and commission must be nonnegative")
        slippage = signed_slippage_fraction(side=side, decision_mid=decision_mid, execution_price=execution_price)
        notional = execution_price * filled_quantity
        total = slippage + commission / notional + financing / notional
        return cls(environment, str(observed_at), order_id, broker_order_id, str(strategy_id), str(model_id),
                   str(model_version), str(instrument), side.strip().upper(), requested_quantity, filled_quantity,
                   decision_mid, execution_price, arrival_spread, slippage, slippage * _BPS,
                   arrival_spread / decision_mid * _BPS, commission, financing, total,
                   slippage * decision_mid * filled_quantity, dict(metadata or {}))

    def to_record(self) -> dict[str, Any]:
        return {
            "environment": self.environment, "observed_at": self.observed_at, "order_id": self.order_id,
            "broker_order_id": self.broker_order_id, "strategy_id": self.strategy_id, "model_id": self.model_id,
            "model_version": self.model_version, "instrument": self.instrument, "side": self.side,
            "requested_quantity": str(self.requested_quantity), "filled_quantity": str(self.filled_quantity),
            "decision_mid": str(self.decision_mid), "execution_price": str(self.execution_price),
            "arrival_spread": str(self.arrival_spread), "slippage_fraction": str(self.slippage_fraction),
            "slippage_bps": str(self.slippage_bps), "spread_bps": str(self.spread_bps),
            "commission": str(self.commission), "financing": str(self.financing),
            "total_cost_fraction": str(self.total_cost_fraction),
            "implementation_shortfall_quote": str(self.implementation_shortfall_quote),
            "metadata": dict(self.metadata),
        }

__all__ = ["TCAObservation", "signed_slippage_fraction"]
