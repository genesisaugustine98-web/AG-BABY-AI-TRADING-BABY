"""Counterpart-style long-running trading node.

The node owns lifecycle, scheduling, event publication and strategy orchestration.
Strategy controllers produce candidates; policy/risk/execution remain the protected
boundary. Execution is opt-in and the repository's execution runtime still enforces
demo/paper restrictions.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from time import sleep, time
from typing import Callable, Protocol

from packages.event_bus import EventBus
from packages.events import (
    ForecastEvent,
    FreezeEvent,
    HeartbeatEvent,
    MarketQuoteEvent,
    OpportunityEvent,
    RiskDecisionEvent,
    OrderLifecycleEvent,
    StrategyDecision,
)
from packages.demo_execution import deterministic_client_order_id
from packages.models import AdmissionContext, InstrumentSpec, MarketState, TradeIntent
from packages.runtime_metrics import RuntimeMetrics
from packages.runtime_supervisor import RuntimeState, RuntimeSupervisor
from packages.strategy_controller import StrategyController


class Clock(Protocol):
    def now_ms(self) -> int:
        ...


class MarketDataFeed(Protocol):
    def quote(self, symbol: str, *, now_ms: int):
        ...

    def completed_bars(self, *, symbol: str, timeframe: str, count: int):
        ...

    def instrument_spec(self, symbol: str) -> InstrumentSpec:
        ...


class ExecutionSink(Protocol):
    def submit(
        self,
        *,
        intent: TradeIntent,
        context: AdmissionContext,
        instrument: InstrumentSpec,
    ):
        ...


class MarketStateFactory(Protocol):
    def __call__(self, *, quote, now_ms: int) -> MarketState: ...


class IntentContextFactory(Protocol):
    def __call__(
        self,
        *,
        decision: StrategyDecision,
        quote,
        market: MarketState,
        now_ms: int,
        instrument: InstrumentSpec,
    ) -> tuple[TradeIntent, AdmissionContext] | None:
        ...


class SystemClock:
    def now_ms(self) -> int:
        return int(time() * 1000)


@dataclass(frozen=True)
class RuntimeConfig:
    node_id: str = "ag-demo-node"
    environment: str = "demo"
    timeframe: str = "H1"
    bars_per_symbol: int = 500
    estimated_cost_fraction: Decimal = Decimal("0.0010")
    safety_margin_fraction: Decimal = Decimal("0.0005")
    allow_execution: bool = False
    heartbeat_interval_ms: int = 5_000
    max_cycles_without_progress: int = 3

    def __post_init__(self) -> None:
        if not self.node_id.strip():
            raise ValueError("node_id is required")
        if self.environment.strip().lower() not in {"demo", "paper"}:
            raise ValueError("runtime environment must be demo or paper")
        if self.bars_per_symbol < 30:
            raise ValueError("bars_per_symbol must be >= 30")
        if self.estimated_cost_fraction < 0 or self.safety_margin_fraction < 0:
            raise ValueError("cost and safety margin must be non-negative")
        if self.allow_execution and self.heartbeat_interval_ms < 1:
            raise ValueError("heartbeat interval must be positive")
        if self.max_cycles_without_progress < 1:
            raise ValueError("max_cycles_without_progress must be >= 1")


class TradingNode:
    def __init__(
        self,
        *,
        config: RuntimeConfig,
        market_data: MarketDataFeed,
        controllers: tuple[StrategyController, ...],
        context_factory: IntentContextFactory,
        execution: ExecutionSink | None = None,
        market_state_factory: MarketStateFactory | None = None,
        clock: Clock | None = None,
        event_bus: EventBus | None = None,
        supervisor: RuntimeSupervisor | None = None,
    ) -> None:
        if config.allow_execution and execution is None:
            raise ValueError("execution sink is required when allow_execution=true")
        self.config = config
        self.market_data = market_data
        self.controllers = controllers
        self.context_factory = context_factory
        self.execution = execution
        self.market_state_factory = market_state_factory
        self.clock = clock or SystemClock()
        self.events = event_bus or EventBus()
        self.supervisor = supervisor or RuntimeSupervisor(
            node_id=config.node_id,
            max_heartbeat_age_ms=max(config.heartbeat_interval_ms * 3, 1_000),
        )
        self._cycle_number = 0
        self.metrics = RuntimeMetrics()

    @property
    def state(self) -> RuntimeState:
        return self.supervisor.state

    def start(self) -> None:
        now = self.clock.now_ms()
        self.supervisor.start()
        self.supervisor.mark_ready(now)

    def cycle(self) -> tuple[object, ...]:
        now_ms = self.clock.now_ms()
        if self.supervisor.state in {RuntimeState.CREATED, RuntimeState.STOPPED}:
            raise RuntimeError("node must be started before cycle")
        self.metrics.start_cycle()
        failures_before = len(self.events.failures())
        try:
            self.supervisor.assert_operational(now_ms)
            result = self._cycle_once(now_ms)
            return result
        except Exception as exc:
            self.metrics.record_cycle_failure()
            self.supervisor.freeze(f"CYCLE_ERROR:{type(exc).__name__}")
            self.metrics.record_freeze()
            try:
                self.events.publish(
                    FreezeEvent(
                        event_id=f"{self.config.node_id}:freeze:{self._cycle_number + 1}",
                        occurred_at_ms=now_ms,
                        source=self.config.node_id,
                        source_version="node-v1",
                        environment=self.config.environment,
                        reason=self.supervisor.reason or type(exc).__name__,
                    )
                )
            finally:
                raise
        finally:
            self.metrics.record_handler_failures(len(self.events.failures()) - failures_before)
            self.metrics.finish_cycle()

    def _cycle_once(self, now_ms: int) -> tuple[object, ...]:
        self._cycle_number += 1
        results: list[object] = []

        for controller in self.controllers:
            symbols = tuple(getattr(controller, "symbols", ()))
            if not symbols:
                raise RuntimeError(
                    f"controller has no symbol universe:{getattr(controller, 'strategy_id', type(controller).__name__)}"
                )

            for symbol in symbols:
                quote = self.market_data.quote(symbol, now_ms=now_ms)
                self.events.publish(
                    MarketQuoteEvent(
                        event_id=f"{self.config.node_id}:quote:{self._cycle_number}:{symbol}",
                        occurred_at_ms=now_ms,
                        source="trading_node",
                        source_version="node-v1",
                        symbol=symbol,
                        bid=str(quote.bid),
                        ask=str(quote.ask),
                        event_time_ms=quote.event_time_ms,
                        usable_at_ms=quote.event_time_ms,
                    )
                )
                bars = self.market_data.completed_bars(
                    symbol=symbol,
                    timeframe=self.config.timeframe,
                    count=self.config.bars_per_symbol,
                )

                quote_age_ms = now_ms - quote.event_time_ms
                if quote_age_ms < 0:
                    self.supervisor.freeze(f"FUTURE_QUOTE:{symbol}")
                    raise RuntimeError(f"future broker quote:{symbol}")
                if self.market_state_factory is not None:
                    market = self.market_state_factory(quote=quote, now_ms=now_ms)
                else:
                    from packages.models import EventState
                    market = MarketState(
                        EventState.NORMAL,
                        quote_age_ms,
                        (quote.ask - quote.bid) / quote.mid,
                        Decimal("0"),
                        Decimal("0"),
                        Decimal("0"),
                        Decimal("0"),
                    )
                decision = controller.evaluate(
                    symbol=symbol,
                    bars=bars,
                    market=market,
                    decision_time_ms=now_ms,
                    estimated_cost=self.config.estimated_cost_fraction,
                    safety_margin=self.config.safety_margin_fraction,
                )
                if decision is None:
                    continue

                self.events.publish(
                    ForecastEvent(
                        event_id=f"{self.config.node_id}:forecast:{self._cycle_number}:{symbol}",
                        occurred_at_ms=now_ms,
                        source=decision.strategy_id,
                        source_version="controller-v1",
                        symbol=symbol,
                        forecast=decision.forecast,
                    )
                )
                self.events.publish(
                    OpportunityEvent(
                        event_id=f"{self.config.node_id}:opportunity:{self._cycle_number}:{symbol}",
                        occurred_at_ms=now_ms,
                        source=decision.strategy_id,
                        source_version="controller-v1",
                        candidate=decision.candidate,
                    )
                )
                results.append(decision)
                self.metrics.record_strategy_decision(admitted=decision.candidate.state == "ADMITTED")

                if not self.config.allow_execution or decision.candidate.state != "ADMITTED":
                    continue
                if self.execution is None:
                    raise RuntimeError("execution sink missing")
                instrument = self.market_data.instrument_spec(symbol)
                built = self.context_factory(
                    decision=decision,
                    quote=quote,
                    market=market,
                    now_ms=now_ms,
                    instrument=instrument,
                )
                if built is None:
                    continue
                intent, context = built
                attempt = self.execution.submit(
                    intent=intent,
                    context=context,
                    instrument=instrument,
                )
                self.metrics.record_execution(outcome=getattr(attempt, "broker_outcome", None) or getattr(attempt, "decision", None))
                if getattr(attempt, "risk", None) is not None:
                    self.events.publish(
                        RiskDecisionEvent(
                            event_id=f"{self.config.node_id}:risk:{self._cycle_number}:{symbol}:{intent.intent_id}",
                            occurred_at_ms=now_ms,
                            source=self.config.node_id,
                            source_version="risk-engine-v1",
                            symbol=symbol,
                            intent_id=intent.intent_id,
                            decision=attempt.risk,
                        )
                    )
                self.events.publish(
                    OrderLifecycleEvent(
                        event_id=f"{self.config.node_id}:order:{self._cycle_number}:{symbol}:{intent.intent_id}",
                        occurred_at_ms=now_ms,
                        source=self.config.node_id,
                        source_version="execution-bridge-v1",
                        client_order_id=deterministic_client_order_id(intent),
                        order_id=getattr(attempt, "order_id", None),
                        state=getattr(attempt, "order_state", None),
                        broker_order_id=getattr(attempt, "broker_order_id", None),
                        outcome=getattr(attempt, "broker_outcome", None),
                        reasons=tuple(getattr(attempt, "reasons", ())),
                    )
                )
                results.append(attempt)

        health = self.supervisor.health(now_ms)
        self.events.publish(
            HeartbeatEvent(
                event_id=f"{self.config.node_id}:heartbeat:{self._cycle_number}",
                occurred_at_ms=now_ms,
                source=self.config.node_id,
                source_version="node-v1",
                node_id=self.config.node_id,
                state=self.supervisor.state.value,
                health="HEALTHY" if health.healthy else (health.reason or "UNHEALTHY"),
            )
        )
        return tuple(results)

    def run(self, *, max_cycles: int | None = None, sleep_seconds: float = 1.0, sleep_fn: Callable[[float], None] = sleep) -> None:
        """Run cycles until stopped, failed, frozen, or max_cycles is reached."""
        if max_cycles is not None and max_cycles < 1:
            raise ValueError("max_cycles must be >= 1 when supplied")
        if sleep_seconds < 0:
            raise ValueError("sleep_seconds must be non-negative")
        if self.supervisor.state in {RuntimeState.CREATED, RuntimeState.STOPPED}:
            self.start()
        count = 0
        while self.supervisor.state == RuntimeState.RUNNING:
            self.cycle()
            count += 1
            if max_cycles is not None and count >= max_cycles:
                return
            sleep_fn(sleep_seconds)

    def stop(self) -> None:
        now = self.clock.now_ms()
        self.supervisor.request_stop(now)
        self.supervisor.complete_stop()


__all__ = [
    "Clock",
    "ExecutionSink",
    "IntentContextFactory",
    "MarketStateFactory",
    "MarketDataFeed",
    "RuntimeConfig",
    "SystemClock",
    "TradingNode",
]
