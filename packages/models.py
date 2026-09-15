from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional, FrozenSet

class Decision(str, Enum):
    APPROVE = 'APPROVE'
    DENY = 'DENY'
    REVIEW = 'REVIEW'

class OrderState(str, Enum):
    CREATED='CREATED'; VALIDATED='VALIDATED'; AUTHORIZED='AUTHORIZED'; SUBMITTING='SUBMITTING'
    ACCEPTED='ACCEPTED'; PARTIAL='PARTIAL'; FILLED='FILLED'; REJECTED='REJECTED'; CANCELED='CANCELED'
    UNKNOWN='UNKNOWN'; RECONCILING='RECONCILING'; FREEZE='FREEZE'

class EventState(str, Enum):
    NORMAL='NORMAL'; PRE_EVENT='PRE_EVENT'; IMMEDIATE_EVENT='IMMEDIATE_EVENT'; POST_EVENT='POST_EVENT'
    RECOVERY='RECOVERY'; CENTRAL_BANK='CENTRAL_BANK'; INTERVENTION_RISK='INTERVENTION_RISK'
    WEEKEND_REOPEN='WEEKEND_REOPEN'; HOLIDAY='HOLIDAY'; FIXING='FIXING'; EXPIRY='EXPIRY'
    BROKER_STRESS='BROKER_STRESS'; DATA_STRESS='DATA_STRESS'

@dataclass(frozen=True)
class Quote:
    symbol: str; bid: Decimal; ask: Decimal; event_time_ms: int; source: str
    @property
    def mid(self) -> Decimal: return (self.bid + self.ask) / Decimal('2')
    @property
    def spread(self) -> Decimal: return self.ask - self.bid

@dataclass(frozen=True)
class InstrumentSpec:
    symbol: str
    base_ccy: str
    quote_ccy: str
    contract_size: Decimal
    point: Decimal
    tick_size: Decimal
    tick_value: Decimal
    min_volume: Decimal
    max_volume: Decimal
    volume_step: Decimal

@dataclass(frozen=True)
class Forecast:
    model_id: str
    version: str
    generated_at_ms: int
    horizon_seconds: int
    expected_return: Decimal
    expected_return_unit: str
    probability_up: Decimal
    calibration_score: Decimal
    confidence: Decimal

@dataclass(frozen=True)
class PortfolioState:
    equity: Decimal
    daily_pnl: Decimal
    gross_risk_fraction: Decimal
    net_usd_factor: Decimal
    open_positions: int
    account_drawdown_fraction: Decimal
    strategy_risk_fraction: Decimal
    frozen: bool = False

@dataclass(frozen=True)
class MarketState:
    event_state: EventState
    quote_age_ms: int
    spread_fraction_of_price: Decimal
    liquidity_score: Decimal
    intervention_score: Decimal
    broker_health: Decimal
    data_health: Decimal

@dataclass(frozen=True)
class TradeIntent:
    intent_id: str; strategy_id: str; strategy_version: str; policy_version: str
    symbol: str; side: str; quantity: Decimal; order_type: str
    limit_price: Optional[Decimal]; stop_price: Decimal; target_price: Optional[Decimal]
    created_at_ms: int; expires_at_ms: int; max_slippage_fraction: Decimal
    risk_fraction: Decimal; horizon_seconds: int
    evidence_ids: FrozenSet[str] = field(default_factory=frozenset)

@dataclass(frozen=True)
class AdmissionContext:
    now_ms: int; quote: Quote; forecast: Forecast; market: MarketState; portfolio: PortfolioState
    estimated_cost_fraction: Decimal; safety_margin_fraction: Decimal
