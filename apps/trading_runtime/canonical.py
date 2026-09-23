"""Canonical turnkey demo-trading composition root.

This module is the single body-system entrypoint for the repository. It binds market data,
strategy training, model governance, allocation, portfolio state, policy/risk execution,
reconciliation, durable events, lifecycle supervision and host singleton control.

It intentionally does not expose a live-trading path. The only broker execution environment
accepted here is demo; the lower execution gateway enforces the same invariant independently.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from decimal import Decimal
from math import sqrt
from typing import Any

from apps.execution_gateway.runtime import DemoExecutionRuntime
from packages.event_bus import EventBus
from packages.events import FreezeEvent, OrderLifecycleEvent, RuntimeManifestEvent
from packages.model_governance import ModelEvidence, ModelGovernance, ModelState
from packages.research_promotion_gate import ResearchPromotionRequirements, evaluate_research_package
from packages.circuit_breaker import CircuitBreakerLimits, ExecutionCircuitBreaker
from packages.config_identity import config_fingerprint
from packages.models import AdmissionContext, EventState, InstrumentSpec, MarketState, PortfolioState, TradeIntent
from packages.portfolio_engine import PortfolioEngine, PositionSnapshot
from packages.portfolio_risk import Exposure, PortfolioRiskEngine, PortfolioRiskLimits, PortfolioRiskDecision
from packages.risk import size_for_cash_risk
from packages.risk_engine import RiskLimits
from packages.strategy_allocator import AllocationLimits
from packages.institutional_risk import InstitutionalAllocationLimits, InstitutionalStrategyAllocator, betas_from_env_payload, correlations_from_env_payload
from packages.strategy_controller import TSMOMController
from packages.tsmom_forecast import PriceBar, TSMOMForecastModel, TSMOMValidation, dataset_fingerprint
from packages.runtime_supervisor import RuntimeState
from packages.fx_valuation import USDConversionGraph
from integrations.runtime_event_store import RuntimeEventStore, attach_runtime_event_store
from integrations.supabase_runtime_lease import SupabaseRuntimeLease, LeaseLost
from integrations.supabase_model_registry import SupabaseModelRegistry
from .metrics_server import MetricsHTTPServer

from .mt5_runtime import MT5RuntimeAdapter
from .node import RuntimeConfig, TradingNode
from .single_instance import SingletonLock


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _decimal_env(name: str, default: Decimal) -> Decimal:
    raw = os.environ.get(name)
    return default if raw is None or not raw.strip() else Decimal(raw.strip())


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return default if raw is None or not raw.strip() else int(raw.strip())


def _symbols_env() -> tuple[str, ...]:
    raw = os.environ.get("AG_SYMBOLS", "")
    symbols = tuple(dict.fromkeys(x.strip().upper() for x in raw.split(",") if x.strip()))
    if not symbols:
        raise RuntimeError("AG_SYMBOLS must contain at least one broker symbol")
    return symbols


@dataclass(frozen=True)
class CanonicalConfig:
    node_id: str
    symbols: tuple[str, ...]
    environment: str = "demo"
    timeframe: str = "H1"
    bars_per_symbol: int = 500
    sleep_seconds: float = 5.0
    allow_execution: bool = False
    estimated_cost_fraction: Decimal = Decimal("0.0010")
    safety_margin_fraction: Decimal = Decimal("0.0005")
    stop_distance_fraction: Decimal = Decimal("0.0020")
    target_multiple: Decimal = Decimal("2.0")
    max_slippage_fraction: Decimal = Decimal("0.0010")
    max_order_risk: Decimal = Decimal("0.01")
    max_total_risk: Decimal = Decimal("0.03")
    max_per_strategy_risk: Decimal = Decimal("0.02")
    max_per_instrument_risk: Decimal = Decimal("0.01")
    risk_max_drawdown: Decimal = Decimal("0.08")
    risk_max_daily_loss: Decimal = Decimal("0.03")
    risk_max_open_positions: int = 8
    risk_min_broker_health: Decimal = Decimal("0.80")
    risk_min_data_health: Decimal = Decimal("0.80")
    emergency_freeze_path: str = "runtime/EMERGENCY_FREEZE"
    max_candidates: int = 8
    tsmom_lookback_bars: int = 24
    tsmom_horizon_bars: int = 6
    tsmom_min_training_samples: int = 30
    bar_interval_seconds: int = 3600
    lock_path: str = "runtime/ag-trading-node.lock"
    event_store_timeout_seconds: float = 10.0
    require_model_governance: bool = True
    governance_min_calibration: Decimal = Decimal("0.65")
    governance_max_drawdown: Decimal = Decimal("0.08")
    portfolio_max_correlation_adjusted_risk: Decimal = Decimal("0.03")
    portfolio_max_abs_net_risk: Decimal = Decimal("0.03")
    portfolio_require_complete_correlations: bool = True
    portfolio_correlations_json: str = "{}"
    distributed_lease: bool = False
    lease_name: str = ""
    lease_ttl_seconds: int = 30
    metrics_enabled: bool = False
    metrics_host: str = "127.0.0.1"
    metrics_port: int = 9300
    max_execution_unknown_outcomes: int = 1
    max_execution_rejections: int = 5
    portfolio_max_gross_notional_fraction: Decimal = Decimal("0.75")
    portfolio_max_net_notional_fraction: Decimal = Decimal("0.35")
    portfolio_max_margin_fraction: Decimal = Decimal("0.45")
    portfolio_max_volatility: Decimal = Decimal("0.20")
    portfolio_max_beta_exposure: Decimal = Decimal("0.25")
    portfolio_betas_json: str = "{}"
    portfolio_fx_symbols: tuple[str, ...] = ()
    research_min_validation_periods: int = 3
    research_min_cost_stress_points: int = 2
    research_min_slippage_stress_points: int = 2

    @classmethod
    def from_env(cls) -> "CanonicalConfig":
        environment = os.environ.get("EXECUTION_ENV", "demo").strip().lower()
        allow_execution = _bool_env("AG_EXECUTION_ENABLED", False)
        config = cls(
            node_id=os.environ.get("AG_NODE_ID", "ag-demo-node").strip(),
            symbols=_symbols_env(),
            environment=environment,
            timeframe=os.environ.get("AG_TIMEFRAME", "H1").strip().upper(),
            bars_per_symbol=_int_env("AG_BARS_PER_SYMBOL", 500),
            sleep_seconds=float(os.environ.get("AG_SLEEP_SECONDS", "5")),
            allow_execution=allow_execution,
            estimated_cost_fraction=_decimal_env("AG_ESTIMATED_COST", Decimal("0.0010")),
            safety_margin_fraction=_decimal_env("AG_SAFETY_MARGIN", Decimal("0.0005")),
            stop_distance_fraction=_decimal_env("AG_STOP_DISTANCE_FRACTION", Decimal("0.0020")),
            target_multiple=_decimal_env("AG_TARGET_MULTIPLE", Decimal("2.0")),
            max_slippage_fraction=_decimal_env("AG_MAX_SLIPPAGE", Decimal("0.0010")),
            max_order_risk=_decimal_env("AG_MAX_ORDER_RISK", Decimal("0.01")),
            max_total_risk=_decimal_env("AG_MAX_TOTAL_RISK", Decimal("0.03")),
            max_per_strategy_risk=_decimal_env("AG_MAX_STRATEGY_RISK", Decimal("0.02")),
            max_per_instrument_risk=_decimal_env("AG_MAX_INSTRUMENT_RISK", Decimal("0.01")),
            risk_max_drawdown=_decimal_env("AG_RISK_MAX_DRAWDOWN", Decimal("0.08")),
            risk_max_daily_loss=_decimal_env("AG_RISK_MAX_DAILY_LOSS", Decimal("0.03")),
            risk_max_open_positions=_int_env("AG_RISK_MAX_OPEN_POSITIONS", 8),
            risk_min_broker_health=_decimal_env("AG_RISK_MIN_BROKER_HEALTH", Decimal("0.80")),
            risk_min_data_health=_decimal_env("AG_RISK_MIN_DATA_HEALTH", Decimal("0.80")),
            emergency_freeze_path=os.environ.get("AG_EMERGENCY_FREEZE_PATH", "runtime/EMERGENCY_FREEZE"),
            max_candidates=_int_env("AG_MAX_CANDIDATES", 8),
            tsmom_lookback_bars=_int_env("AG_TSMOM_LOOKBACK", 24),
            tsmom_horizon_bars=_int_env("AG_TSMOM_HORIZON", 6),
            tsmom_min_training_samples=_int_env("AG_TSMOM_MIN_SAMPLES", 30),
            bar_interval_seconds=_int_env("AG_BAR_INTERVAL_SECONDS", 3600),
            lock_path=os.environ.get("AG_RUNTIME_LOCK_PATH", "runtime/ag-trading-node.lock"),
            event_store_timeout_seconds=float(os.environ.get("AG_EVENT_STORE_TIMEOUT", "10")),
            require_model_governance=_bool_env("AG_REQUIRE_MODEL_GOVERNANCE", True),
            governance_min_calibration=_decimal_env("AG_MIN_CALIBRATION", Decimal("0.65")),
            governance_max_drawdown=_decimal_env("AG_MAX_PROMOTION_DRAWDOWN", Decimal("0.08")),
            portfolio_max_correlation_adjusted_risk=_decimal_env("AG_MAX_CORR_ADJUSTED_RISK", Decimal("0.03")),
            portfolio_max_abs_net_risk=_decimal_env("AG_MAX_ABS_NET_RISK", Decimal("0.03")),
            portfolio_require_complete_correlations=_bool_env("AG_REQUIRE_COMPLETE_CORRELATIONS", True),
            portfolio_correlations_json=os.environ.get("AG_PORTFOLIO_CORRELATIONS", "{}"),
            distributed_lease=_bool_env("AG_DISTRIBUTED_LEASE", False),
            lease_name=os.environ.get("AG_LEASE_NAME", "").strip(),
            lease_ttl_seconds=_int_env("AG_LEASE_TTL_SECONDS", 30),
            metrics_enabled=_bool_env("AG_METRICS_ENABLED", False),
            metrics_host=os.environ.get("AG_METRICS_HOST", "127.0.0.1").strip(),
            metrics_port=_int_env("AG_METRICS_PORT", 9300),
            max_execution_unknown_outcomes=_int_env("AG_MAX_EXECUTION_UNKNOWN", 1),
            max_execution_rejections=_int_env("AG_MAX_EXECUTION_REJECTIONS", 5),
            portfolio_max_gross_notional_fraction=_decimal_env("AG_MAX_GROSS_NOTIONAL", Decimal("0.75")),
            portfolio_max_net_notional_fraction=_decimal_env("AG_MAX_NET_NOTIONAL", Decimal("0.35")),
            portfolio_max_margin_fraction=_decimal_env("AG_MAX_MARGIN_FRACTION", Decimal("0.45")),
            portfolio_max_volatility=_decimal_env("AG_MAX_PORTFOLIO_VOL", Decimal("0.20")),
            portfolio_max_beta_exposure=_decimal_env("AG_MAX_PORTFOLIO_BETA", Decimal("0.25")),
            portfolio_betas_json=os.environ.get("AG_PORTFOLIO_BETAS", "{}"),
            portfolio_fx_symbols=tuple(dict.fromkeys(x.strip().upper() for x in os.environ.get("AG_PORTFOLIO_FX_SYMBOLS", "").split(",") if x.strip())),
            research_min_validation_periods=_int_env("AG_RESEARCH_MIN_VALIDATION_PERIODS", 3),
            research_min_cost_stress_points=_int_env("AG_RESEARCH_MIN_COST_STRESS_POINTS", 2),
            research_min_slippage_stress_points=_int_env("AG_RESEARCH_MIN_SLIPPAGE_STRESS_POINTS", 2),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if not self.node_id:
            raise ValueError("node_id is required")
        if self.environment != "demo":
            raise ValueError("canonical MT5 runtime only permits the demo environment")
        if self.timeframe != "H1":
            raise ValueError("canonical MT5 strategy entrypoint currently requires H1")
        if self.bars_per_symbol < 100:
            raise ValueError("bars_per_symbol must be >= 100 for governance-backed startup")
        if self.sleep_seconds < 0:
            raise ValueError("sleep_seconds must be non-negative")
        for name, value in (
            ("estimated_cost_fraction", self.estimated_cost_fraction),
            ("safety_margin_fraction", self.safety_margin_fraction),
            ("stop_distance_fraction", self.stop_distance_fraction),
            ("max_slippage_fraction", self.max_slippage_fraction),
            ("max_order_risk", self.max_order_risk),
            ("max_total_risk", self.max_total_risk),
            ("max_per_strategy_risk", self.max_per_strategy_risk),
            ("max_per_instrument_risk", self.max_per_instrument_risk),
            ("risk_max_drawdown", self.risk_max_drawdown),
            ("risk_max_daily_loss", self.risk_max_daily_loss),
            ("risk_min_broker_health", self.risk_min_broker_health),
            ("risk_min_data_health", self.risk_min_data_health),
            ("governance_min_calibration", self.governance_min_calibration),
            ("governance_max_drawdown", self.governance_max_drawdown),
            ("portfolio_max_correlation_adjusted_risk", self.portfolio_max_correlation_adjusted_risk),
            ("portfolio_max_abs_net_risk", self.portfolio_max_abs_net_risk),
            ("portfolio_max_gross_notional_fraction", self.portfolio_max_gross_notional_fraction),
            ("portfolio_max_net_notional_fraction", self.portfolio_max_net_notional_fraction),
            ("portfolio_max_margin_fraction", self.portfolio_max_margin_fraction),
            ("portfolio_max_volatility", self.portfolio_max_volatility),
            ("portfolio_max_beta_exposure", self.portfolio_max_beta_exposure),
        ):
            if not value.is_finite() or value < 0 or value > Decimal("1"):
                raise ValueError(f"{name} must be a finite fraction in [0,1]")
        if self.target_multiple <= 0 or self.max_candidates < 1 or self.risk_max_open_positions < 1:
            raise ValueError("target_multiple, max_candidates and risk_max_open_positions must be positive")
        if self.max_order_risk > self.max_per_strategy_risk:
            raise ValueError("max_order_risk cannot exceed max_per_strategy_risk")
        if self.max_per_strategy_risk > self.max_total_risk:
            raise ValueError("max_per_strategy_risk cannot exceed max_total_risk")
        if self.max_per_instrument_risk > self.max_total_risk:
            raise ValueError("max_per_instrument_risk cannot exceed max_total_risk")
        if self.portfolio_max_net_notional_fraction > self.portfolio_max_gross_notional_fraction:
            raise ValueError("portfolio net-notional limit cannot exceed gross-notional limit")
        if self.tsmom_lookback_bars < 2 or self.tsmom_horizon_bars < 1 or self.tsmom_min_training_samples < 10:
            raise ValueError("invalid TSMOM configuration")
        if self.distributed_lease:
            if not self.lease_name:
                raise ValueError("AG_LEASE_NAME is required when distributed lease is enabled")
            if self.lease_ttl_seconds < 5 or self.lease_ttl_seconds > 300:
                raise ValueError("lease_ttl_seconds must be between 5 and 300")
        if self.metrics_enabled:
            if self.metrics_host not in {"127.0.0.1", "::1", "localhost"}:
                raise ValueError("metrics_host must remain loopback-only")
            if self.metrics_port < 1024 or self.metrics_port > 65535:
                raise ValueError("metrics_port must be between 1024 and 65535")
        if self.max_execution_unknown_outcomes < 1 or self.max_execution_rejections < 1:
            raise ValueError("execution circuit breaker thresholds must be >= 1")
        if self.research_min_validation_periods < 1 or self.research_min_cost_stress_points < 1 or self.research_min_slippage_stress_points < 1:
            raise ValueError("research evidence thresholds must be >= 1")


class CanonicalMarketStateFactory:
    def __init__(self, gateway: DemoExecutionRuntime, *, full_liquidity_spread: Decimal = Decimal("0.00015"),
                 blocked_spread: Decimal = Decimal("0.00030"), max_quote_age_ms: int = 1500) -> None:
        self.gateway = gateway
        self.full_liquidity_spread = full_liquidity_spread
        self.blocked_spread = blocked_spread
        self.max_quote_age_ms = max_quote_age_ms

    def __call__(self, *, quote, now_ms: int) -> MarketState:
        if quote.bid <= 0 or quote.ask <= 0:
            raise RuntimeError("non-positive broker quote")
        if quote.ask < quote.bid:
            raise RuntimeError("crossed broker quote")
        if not str(quote.source).strip():
            raise RuntimeError("quote source is required")
        age = now_ms - quote.event_time_ms
        spread_fraction = quote.spread / quote.mid
        if age < 0:
            raise RuntimeError("negative quote age")
        if age <= self.max_quote_age_ms:
            data_health = Decimal("1")
        else:
            data_health = max(Decimal("0"), Decimal("1") - (Decimal(age - self.max_quote_age_ms) / Decimal("5000")))
        if not self.gateway.gateway.connected:
            broker_health = Decimal("0")
        else:
            broker_health = Decimal("1")
        if spread_fraction <= self.full_liquidity_spread:
            liquidity = Decimal("1")
        elif spread_fraction >= self.blocked_spread:
            liquidity = Decimal("0")
        else:
            liquidity = (
                Decimal("1")
                - (spread_fraction - self.full_liquidity_spread)
                / (self.blocked_spread - self.full_liquidity_spread)
            )
        event_state = EventState.NORMAL
        if spread_fraction >= self.blocked_spread:
            event_state = EventState.BROKER_STRESS
        elif age > self.max_quote_age_ms:
            event_state = EventState.DATA_STRESS
        return MarketState(
            event_state,
            age,
            spread_fraction,
            max(Decimal("0"), min(Decimal("1"), liquidity)),
            Decimal("0"),
            broker_health,
            data_health,
        )


class CanonicalIntentFactory:
    def __init__(self, portfolio: PortfolioEngine, config: CanonicalConfig) -> None:
        self.portfolio = portfolio
        self.config = config

    def __call__(self, *, decision, quote, market, now_ms: int, instrument: InstrumentSpec):
        candidate = decision.candidate
        portfolio_state = self.portfolio.as_portfolio_state(captured_at_ms=now_ms)
        risk_fraction = min(candidate.suggested_risk, self.config.max_order_risk)
        if risk_fraction <= 0:
            return None

        stop_distance = max(
            quote.mid * self.config.stop_distance_fraction,
            quote.spread * Decimal("4"),
            instrument.tick_size,
        )
        if candidate.side == "BUY":
            stop_price = quote.mid - stop_distance
            target_price = quote.mid + stop_distance * self.config.target_multiple
        else:
            stop_price = quote.mid + stop_distance
            target_price = quote.mid - stop_distance * self.config.target_multiple

        quantity = size_for_cash_risk(
            instrument,
            portfolio_state.equity,
            risk_fraction,
            stop_distance,
        )
        if quantity <= 0:
            return None

        intent_id = f"intent-{candidate.candidate_id}"
        intent = TradeIntent(
            intent_id,
            candidate.strategy_id,
            candidate.model_version,
            "policy-v2",
            candidate.instrument,
            candidate.side,
            quantity,
            "MARKET",
            None,
            stop_price,
            target_price,
            now_ms,
            min(now_ms + decision.forecast.horizon_seconds * 1000, now_ms + 86_400_000),
            self.config.max_slippage_fraction,
            risk_fraction,
            decision.forecast.horizon_seconds,
            frozenset(decision.evidence_ids),
        )
        context = AdmissionContext(
            now_ms,
            quote,
            decision.forecast,
            market,
            portfolio_state,
            self.config.estimated_cost_fraction,
            self.config.safety_margin_fraction,
        )
        return intent, context


class CanonicalPortfolioRiskGate:
    """Exact post-sizing portfolio risk gate using broker-valued positions and realized volatility."""

    def __init__(
        self,
        portfolio: PortfolioEngine,
        market_data: MT5RuntimeAdapter,
        config: CanonicalConfig,
    ) -> None:
        self.portfolio = portfolio
        self.market_data = market_data
        self.config = config
        self.correlations = correlations_from_env_payload(config.portfolio_correlations_json)
        self.betas = betas_from_env_payload(config.portfolio_betas_json)
        self.fx_symbols = config.portfolio_fx_symbols
        self.engine = PortfolioRiskEngine(
            PortfolioRiskLimits(
                max_gross_notional_fraction=config.portfolio_max_gross_notional_fraction,
                max_abs_net_notional_fraction=config.portfolio_max_net_notional_fraction,
                max_margin_fraction=config.portfolio_max_margin_fraction,
                max_portfolio_volatility=config.portfolio_max_volatility,
                max_abs_beta_exposure=config.portfolio_max_beta_exposure,
                require_complete_correlation=config.portfolio_require_complete_correlations,
            )
        )

    def __call__(
        self,
        *,
        candidate,
        intent,
        quote,
        market,
        instrument,
        now_ms: int,
    ) -> PortfolioRiskDecision:
        fx = USDConversionGraph()
        for fx_symbol in self.fx_symbols:
            fx_spec = self.market_data.instrument_spec(fx_symbol)
            fx_quote = self.market_data.quote(fx_symbol, now_ms=now_ms)
            fx.add_pair(fx_spec.symbol, fx_quote.mid)
        exposures: list[Exposure] = []
        for position in self.portfolio.position_snapshots():
            if position.net_quantity == 0:
                continue
            spec = self.market_data.instrument_spec(position.instrument)
            position_quote = self.market_data.quote(position.instrument, now_ms=now_ms)
            bars = self.market_data.completed_bars(
                symbol=position.instrument,
                timeframe=self.config.timeframe,
                count=self.config.bars_per_symbol,
            )
            notional = self._usd_notional(
                quantity=position.net_quantity,
                quote=position_quote,
                spec=spec,
                fx=fx,
            )
            exposures.append(
                Exposure(
                    position.instrument,
                    notional,
                    self._realized_volatility(bars),
                    self.betas.get(position.instrument.upper(), Decimal("0")),
                )
            )

        candidate_notional = self._usd_notional(
            quantity=intent.quantity if intent.side.upper() == "BUY" else -intent.quantity,
            quote=quote,
            spec=instrument,
            fx=fx,
        )
        exposures.append(
            Exposure(
                intent.symbol,
                candidate_notional,
                self._realized_volatility(
                    self.market_data.completed_bars(
                        symbol=intent.symbol,
                        timeframe=self.config.timeframe,
                        count=self.config.bars_per_symbol,
                    )
                ),
                self.betas.get(intent.symbol.upper(), Decimal("0")),
            )
        )

        return self.engine.evaluate(
            exposures=tuple(exposures),
            account_equity=self.portfolio.snapshot(captured_at_ms=now_ms).equity,
            margin_fraction=self.portfolio.margin_fraction(),
            correlation=self.correlations,
        )

    @staticmethod
    def _usd_notional(*, quantity: Decimal, quote, spec: InstrumentSpec, fx: USDConversionGraph) -> Decimal:
        units = quantity * spec.contract_size
        base = spec.base_ccy.upper()
        quote_ccy = spec.quote_ccy.upper()
        if quote_ccy == "USD":
            return units * quote.mid
        if base == "USD":
            return units
        try:
            return fx.quote_notional_usd(base_ccy=base, quote_ccy=quote_ccy, units=units, price=quote.mid)
        except RuntimeError as exc:
            raise RuntimeError(f"portfolio USD valuation unavailable:{spec.symbol}:{base}/{quote_ccy}") from exc

    def _realized_volatility(self, bars) -> Decimal:
        closes = [Decimal(str(getattr(bar, "close"))) for bar in bars if Decimal(str(getattr(bar, "close"))) > 0]
        if len(closes) < 20:
            raise RuntimeError("insufficient bars for portfolio volatility")
        returns = [closes[i] / closes[i - 1] - Decimal("1") for i in range(1, len(closes))]
        mean = sum(returns, Decimal("0")) / Decimal(len(returns))
        variance = sum((value - mean) ** 2 for value in returns) / Decimal(max(1, len(returns) - 1))
        annualization = Decimal(str(sqrt((86_400 / self.config.bar_interval_seconds) * 252)))
        return max(Decimal("0.000001"), variance.sqrt() * annualization)


class CanonicalTradingSystem:
    def __init__(
        self,
        *,
        config: CanonicalConfig,
        runtime: DemoExecutionRuntime,
        node: TradingNode,
        portfolio: PortfolioEngine,
        lock: SingletonLock,
        event_bus: EventBus,
    ) -> None:
        self.config = config
        self.runtime = runtime
        self.node = node
        self.portfolio = portfolio
        self.lock = lock
        self.event_bus = event_bus
        self._closed = False
        self._lease: SupabaseRuntimeLease | None = None
        self._metrics_server: MetricsHTTPServer | None = None
        self._circuit_breaker: ExecutionCircuitBreaker | None = None

    @classmethod
    def create(cls, config: CanonicalConfig) -> "CanonicalTradingSystem":
        config.validate()
        lock = SingletonLock(config.lock_path)
        lock.acquire()
        runtime: DemoExecutionRuntime | None = None
        lease: SupabaseRuntimeLease | None = None
        metrics_server: MetricsHTTPServer | None = None
        try:
            if config.distributed_lease:
                lease = SupabaseRuntimeLease(
                    environment=config.environment,
                    lease_name=config.lease_name,
                    owner_id=config.node_id,
                    ttl_seconds=config.lease_ttl_seconds,
                )
                lease.acquire()
            runtime = DemoExecutionRuntime.create(
                risk_limits=RiskLimits(
                    max_order_risk=config.max_order_risk,
                    max_strategy_risk=config.max_per_strategy_risk,
                    max_gross_risk=config.max_total_risk,
                    max_drawdown=config.risk_max_drawdown,
                    max_daily_loss=config.risk_max_daily_loss,
                    max_open_positions=config.risk_max_open_positions,
                    min_broker_health=config.risk_min_broker_health,
                    min_data_health=config.risk_min_data_health,
                )
            )
            event_bus = EventBus(history_limit=2000)
            store = RuntimeEventStore(
                environment=config.environment,
                timeout_seconds=config.event_store_timeout_seconds,
            )
            attach_runtime_event_store_critical(event_bus, store)
            model_registry = SupabaseModelRegistry(timeout_seconds=config.event_store_timeout_seconds)

            portfolio = PortfolioEngine()
            _refresh_portfolio(runtime, portfolio)

            controllers: list[TSMOMController] = []
            for symbol in config.symbols:
                gateway = runtime.gateway
                feed = MT5RuntimeAdapter(gateway)
                bars = feed.completed_bars(
                    symbol=symbol,
                    timeframe=config.timeframe,
                    count=config.bars_per_symbol,
                )
                model = TSMOMForecastModel(
                    lookback_bars=config.tsmom_lookback_bars,
                    horizon_bars=config.tsmom_horizon_bars,
                    min_training_samples=config.tsmom_min_training_samples,
                    bar_interval_seconds=config.bar_interval_seconds,
                )
                validation = model.fit(
                    bars,
                    dataset_fingerprint=dataset_fingerprint(bars),
                    code_commit_sha=os.environ.get("GIT_COMMIT_SHA", "runtime"),
                )
                model_registry.record_validation(
                    model_id=validation.model_id,
                    version=validation.version,
                    validation=validation,
                    status="candidate",
                    governance_state=ModelState.CANDIDATE.value,
                )
                if config.allow_execution and config.require_model_governance:
                    _require_demo_governance(config, validation)
                    model_registry.record_validation(
                        model_id=validation.model_id,
                        version=validation.version,
                        validation=validation,
                        status="validated",
                        governance_state=ModelState.DEMO.value,
                    )
                controllers.append(TSMOMController(model=model, symbols=(symbol,)))

            feed = MT5RuntimeAdapter(runtime.gateway)
            correlations = correlations_from_env_payload(config.portfolio_correlations_json)
            allocator = InstitutionalStrategyAllocator(
                InstitutionalAllocationLimits(
                    max_total_risk=config.max_total_risk,
                    max_per_strategy_risk=config.max_per_strategy_risk,
                    max_per_instrument_risk=config.max_per_instrument_risk,
                    max_candidates=config.max_candidates,
                    max_correlation_adjusted_risk=config.portfolio_max_correlation_adjusted_risk,
                    max_abs_net_risk=config.portfolio_max_abs_net_risk,
                    require_complete_correlations=config.portfolio_require_complete_correlations,
                ),
                correlations=correlations,
                current_risk_provider=lambda: portfolio.snapshot().gross_risk_fraction,
            )
            node = TradingNode(
                config=RuntimeConfig(
                    node_id=config.node_id,
                    environment=config.environment,
                    timeframe=config.timeframe,
                    bars_per_symbol=config.bars_per_symbol,
                    estimated_cost_fraction=config.estimated_cost_fraction,
                    safety_margin_fraction=config.safety_margin_fraction,
                    allow_execution=config.allow_execution,
                    config_fingerprint=config_fingerprint(config),
                    emergency_freeze_path=config.emergency_freeze_path,
                ),
                market_data=feed,
                controllers=tuple(controllers),
                context_factory=CanonicalIntentFactory(portfolio, config),
                execution=runtime,
                market_state_factory=CanonicalMarketStateFactory(runtime),
                allocator=allocator,
                strategy_order=tuple(c.strategy_id for c in controllers),
                portfolio_risk_gate=CanonicalPortfolioRiskGate(portfolio, feed, config),
                execution_guard=(lambda: lease.renew()) if lease is not None else None,
                event_bus=event_bus,
            )

            def trip_execution(reason: str) -> None:
                node.supervisor.freeze(reason)
                runtime.safety.set_frozen(True, reason=reason)

            circuit_breaker = ExecutionCircuitBreaker(
                CircuitBreakerLimits(
                    max_unknown_outcomes=config.max_execution_unknown_outcomes,
                    max_rejected_outcomes=config.max_execution_rejections,
                ),
                trip_callback=trip_execution,
            )
            event_bus.subscribe(OrderLifecycleEvent, circuit_breaker.observe, critical=True)

            system = cls(
                config=config,
                runtime=runtime,
                node=node,
                portfolio=portfolio,
                lock=lock,
                event_bus=event_bus,
            )
            system._lease = lease
            system._circuit_breaker = circuit_breaker
            model_identities = tuple(
                sorted(
                    f"{getattr(controller.model, 'MODEL_ID', 'unknown')}:{getattr(controller.model, 'VERSION', 'unknown')}"
                    for controller in controllers
                )
            )
            event_bus.publish(
                RuntimeManifestEvent(
                    event_id=node._event_id("runtime-manifest"),
                    occurred_at_ms=node.clock.now_ms(),
                    source=config.node_id,
                    source_version=f"canonical-v1:{node.config_fingerprint}",
                    runtime_instance_id=node.runtime_instance_id,
                    config_fingerprint=node.config_fingerprint,
                    git_commit_sha=os.environ.get("GIT_COMMIT_SHA", "runtime"),
                    environment=config.environment,
                    model_identities=model_identities,
                )
            )
            if config.metrics_enabled:
                metrics_server = MetricsHTTPServer(
                    host=config.metrics_host,
                    port=config.metrics_port,
                    snapshot_provider=lambda: {
                        "healthy": system.node.supervisor.health(system.node.clock.now_ms()).healthy,
                        "ready": system.node.state == RuntimeState.RUNNING,
                        "state": system.node.state.value,
                        "cycles": system.node.metrics.snapshot().cycles,
                        "cycle_failures": system.node.metrics.snapshot().cycle_failures,
                        "execution_attempts": system.node.metrics.snapshot().execution_attempts,
                        "execution_unknown": system.node.metrics.snapshot().execution_unknown,
                        "freezes": system.node.metrics.snapshot().freezes,
                    },
                )
                metrics_server.start()
                system._metrics_server = metrics_server
            return system
        except Exception:
            if runtime is not None:
                try:
                    runtime.close()
                except Exception:
                    pass
            if metrics_server is not None:
                try:
                    metrics_server.close()
                except Exception:
                    pass
            if lease is not None:
                try:
                    lease.release()
                except Exception:
                    pass
            lock.release()
            raise

    def start(self) -> None:
        if self._closed:
            raise RuntimeError("canonical runtime is closed")
        if self.node.state in {RuntimeState.CREATED, RuntimeState.STOPPED}:
            self._renew_lease_or_fail()
            self._reconcile_and_refresh()
            self.node.start()

    def run(self, *, max_cycles: int | None = None) -> None:
        if max_cycles is not None and max_cycles < 1:
            raise ValueError("max_cycles must be >= 1 when supplied")
        self.start()
        count = 0
        try:
            while self.node.state == RuntimeState.RUNNING:
                self._renew_lease_or_fail()
                self._reconcile_and_refresh()
                self.node.cycle()
                count += 1
                if max_cycles is not None and count >= max_cycles:
                    return
                if self.config.sleep_seconds:
                    import time
                    time.sleep(self.config.sleep_seconds)
        except Exception as exc:
            reason = f"CANONICAL_RUNTIME_FAILURE:{type(exc).__name__}"
            self.node.supervisor.freeze(reason)
            try:
                self.runtime.safety.set_frozen(True, reason=reason)
            finally:
                self.event_bus.publish(
                    FreezeEvent(
                        event_id=self.node._event_id(f"canonical-freeze:{self.node._cycle_number + 1}"),
                        occurred_at_ms=self.node.clock.now_ms(),
                        source=self.config.node_id,
                        source_version=f"canonical-v1:{self.node.config_fingerprint}",
                        environment=self.config.environment,
                        reason=reason,
                    )
                )
            raise
        finally:
            self.close()

    def stop(self) -> None:
        if self._closed:
            return
        reason = "CANONICAL_RUNTIME_STOP_REQUESTED"
        try:
            self.runtime.safety.set_frozen(True, reason=reason)
        finally:
            self.node.stop()
            self.close()

    def _renew_lease_or_fail(self) -> None:
        if self._lease is None:
            return
        try:
            self._lease.renew()
        except LeaseLost as exc:
            reason = "RUNTIME_LEASE_LOST"
            self.node.supervisor.freeze(reason)
            self.runtime.safety.set_frozen(True, reason=reason)
            raise RuntimeError(reason) from exc

    def _reconcile_and_refresh(self) -> None:
        result = self.runtime.reconciliation.reconcile_once()
        if result.freeze_required or not self.runtime.reconciliation.trading_permitted:
            self.node.supervisor.freeze("BROKER_RECONCILIATION_NOT_CLEAN")
            raise RuntimeError("broker reconciliation did not establish trading readiness")
        _refresh_portfolio(self.runtime, self.portfolio)

    def close(self) -> None:
        if self._closed:
            return
        try:
            self.runtime.close()
        finally:
            try:
                if self._metrics_server is not None:
                    self._metrics_server.close()
            finally:
                try:
                    if self._lease is not None:
                        self._lease.release()
                finally:
                    self.lock.release()
                self._closed = True


def _refresh_portfolio(runtime: DemoExecutionRuntime, portfolio: PortfolioEngine) -> None:
    captured_at_ms = int(__import__("time").time() * 1000)
    account = runtime.gateway.account_snapshot()
    runtime.safety.record_account_snapshot(account)
    if not bool(account.get("trade_allowed", False)):
        portfolio.freeze()
        raise RuntimeError("broker account trading is not allowed")
    equity = Decimal(str(account["equity"]))
    balance = Decimal(str(account["balance"]))
    portfolio.update_account(
        captured_at_ms=captured_at_ms,
        balance=balance,
        equity=equity,
        margin=Decimal(str(account.get("margin", "0"))),
    )
    snapshot = runtime.gateway.snapshot()
    positions = tuple(
        PositionSnapshot(position.instrument, position.net_quantity)
        for position in snapshot.positions
    )
    portfolio.update_positions(
        positions,
        captured_at_ms=captured_at_ms,
    )

    # Rebuild risk reservations from durable nonterminal orders. This prevents a
    # process restart from forgetting risk already committed to live/pending demo orders.
    portfolio.reset_order_risk_reservations()
    portfolio.reset_strategy_risk()
    strategy_totals: dict[str, Decimal] = {}
    if hasattr(runtime.orders, "active_order_risk_reservations"):
        for order_id, strategy_id, risk in runtime.orders.active_order_risk_reservations():
            portfolio.reserve_order_risk(order_id, risk)
            strategy_totals[strategy_id] = strategy_totals.get(strategy_id, Decimal("0")) + risk
    for strategy_id, risk in strategy_totals.items():
        portfolio.set_strategy_risk(strategy_id, risk)


def _require_demo_governance(config: CanonicalConfig, validation: TSMOMValidation) -> None:
    raw = os.environ.get("AG_MODEL_EVIDENCE_JSON", "")
    if not raw.strip():
        raise RuntimeError("AG_MODEL_EVIDENCE_JSON is required before demo execution")
    try:
        supplied = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("AG_MODEL_EVIDENCE_JSON is invalid JSON") from exc
    if not isinstance(supplied, dict):
        raise RuntimeError("AG_MODEL_EVIDENCE_JSON must be an object")

    research_decision = evaluate_research_package(
        supplied,
        requirements=ResearchPromotionRequirements(
            min_independent_validation_periods=config.research_min_validation_periods,
            min_cost_stress_points=config.research_min_cost_stress_points,
            min_slippage_stress_points=config.research_min_slippage_stress_points,
        ),
    )
    if not research_decision.allowed:
        raise RuntimeError("RESEARCH_PROMOTION_BLOCKED:" + "|".join(research_decision.reasons))

    def flag(name: str):
        return bool(supplied.get(name, False))

    evidence = ModelEvidence(
        point_in_time=flag("point_in_time"),
        walk_forward=flag("walk_forward"),
        purged_validation=flag("purged_validation"),
        costs_modeled=flag("costs_modeled"),
        slippage_modeled=flag("slippage_modeled"),
        multiple_testing_controlled=flag("multiple_testing_controlled"),
        calibrated=flag("calibrated"),
        stress_tested=flag("stress_tested"),
        calibration_score=validation.calibration_score,
        max_drawdown_fraction=Decimal(str(supplied.get("max_drawdown_fraction", "1"))),
        demo_validated=flag("demo_validated"),
        data_fingerprint=str(supplied.get("data_fingerprint") or validation.dataset_fingerprint),
        code_commit_sha=str(supplied.get("code_commit_sha") or validation.code_commit_sha),
    )
    governance = ModelGovernance(
        minimum_calibration_score=config.governance_min_calibration,
        maximum_promotable_drawdown=config.governance_max_drawdown,
    )
    current = ModelState.CANDIDATE
    for target in (ModelState.VALIDATED, ModelState.SHADOW, ModelState.PAPER, ModelState.DEMO):
        decision = governance.transition(current=current, target=target, evidence=evidence)
        if not decision.allowed:
            raise RuntimeError("MODEL_GOVERNANCE_BLOCKED:" + "|".join(decision.reasons))
        current = target


def attach_runtime_event_store_critical(bus: EventBus, store: RuntimeEventStore):
    """Persist every runtime event as a safety-critical observer.

    Unlike the historical helper, persistence failure is not swallowed: the node freezes
    instead of continuing with an incomplete audit trail.
    """
    return bus.subscribe(None, store.append, critical=True)


__all__ = ["CanonicalConfig", "CanonicalTradingSystem", "CanonicalIntentFactory", "CanonicalMarketStateFactory"]
