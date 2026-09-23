"""Typed runtime events shared by data, strategy, risk, execution and supervision."""
from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet

from .models import Forecast, OrderState
from .opportunity import OpportunityCandidate
from .risk_engine import RiskDecision


@dataclass(frozen=True)
class RuntimeEvent:
    event_id: str
    occurred_at_ms: int
    source: str
    source_version: str

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("event_id is required")
        if self.occurred_at_ms <= 0:
            raise ValueError("occurred_at_ms must be positive")
        if not self.source.strip() or not self.source_version.strip():
            raise ValueError("event provenance is required")


@dataclass(frozen=True)
class MarketQuoteEvent(RuntimeEvent):
    symbol: str
    bid: str
    ask: str
    event_time_ms: int
    usable_at_ms: int


@dataclass(frozen=True)
class ForecastEvent(RuntimeEvent):
    symbol: str
    forecast: Forecast


@dataclass(frozen=True)
class OpportunityEvent(RuntimeEvent):
    candidate: OpportunityCandidate


@dataclass(frozen=True)
class AllocationDecisionEvent(RuntimeEvent):
    candidate_id: str
    strategy_id: str
    symbol: str
    approved: bool
    reason: str


@dataclass(frozen=True)
class PortfolioRiskDecisionEvent(RuntimeEvent):
    candidate_id: str
    symbol: str
    approved: bool
    reasons: tuple[str, ...]
    gross_fraction: str
    net_fraction: str
    margin_fraction: str
    portfolio_volatility: str
    beta_exposure: str


@dataclass(frozen=True)
class RiskDecisionEvent(RuntimeEvent):
    symbol: str
    intent_id: str
    decision: RiskDecision


@dataclass(frozen=True)
class OrderLifecycleEvent(RuntimeEvent):
    client_order_id: str
    order_id: str | None
    state: OrderState | None
    broker_order_id: str | None
    outcome: str | None
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReconciliationEvent(RuntimeEvent):
    environment: str
    status: str
    frozen: bool
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class FreezeEvent(RuntimeEvent):
    environment: str
    reason: str


@dataclass(frozen=True)
class HeartbeatEvent(RuntimeEvent):
    node_id: str
    state: str
    health: str


@dataclass(frozen=True)
class StrategyDecision:
    strategy_id: str
    symbol: str
    forecast: Forecast
    candidate: OpportunityCandidate
    evidence_ids: FrozenSet[str] = frozenset()


__all__ = [
    "RuntimeEvent",
    "MarketQuoteEvent",
    "ForecastEvent",
    "OpportunityEvent",
    "AllocationDecisionEvent",
    "PortfolioRiskDecisionEvent",
    "RiskDecisionEvent",
    "OrderLifecycleEvent",
    "ReconciliationEvent",
    "FreezeEvent",
    "HeartbeatEvent",
    "StrategyDecision",
]
