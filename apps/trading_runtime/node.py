"""Canonical long-running trading node.

The node owns lifecycle, scheduling and event publication. Strategy controllers only produce
auditable candidates; allocation happens before any order context is built; policy/risk and
durable execution remain the protected boundary. The runtime environment is restricted to
demo/paper by configuration and the execution gateway separately enforces demo-only broker use.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from time import sleep, time
from uuid import uuid4
from typing import Callable, Protocol

from packages.event_bus import EventBus
from packages.events import (
    AllocationDecisionEvent,
    ForecastEvent,
    FreezeEvent,
    HeartbeatEvent,
    MarketQuoteEvent,
    OpportunityEvent,
    OrderLifecycleEvent,
    RiskDecisionEvent,
    StrategyDecision,
)
from packages.demo_execution import deterministic_client_order_id
from packages.models import AdmissionContext, InstrumentSpec, MarketState, TradeIntent
from packages.opportunity import OpportunityCandidate
from packages.runtime_metrics import RuntimeMetrics
from packages.runtime_supervisor import RuntimeState, RuntimeSupervisor
from packages.strategy_allocator import AllocationResult
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


class CandidateAllocator(Protocol):
    def allocate(
        self,
        *,
        candidates: tuple[OpportunityCandidate, ...],
        strategy_order: tuple[str, ...],
    ) -> AllocationResult:
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
    def __init__(self, *, max_backward_ms: int = 1_000, max_forward_jump_ms: int = 1_800_000) -> None:
        self.max_backward_ms = max_backward_ms
        self.max_forward_jump_ms = max_forward_jump_ms
        self._last_ms: int | None = None

    def now_ms(self) -> int:
        current = int(time() * 1000)
        if self._last_ms is not None:
            if current + self.max_backward_ms < self._last_ms:
                raise RuntimeError("SYSTEM_CLOCK_MOVED_BACKWARD")
            if current - self._last_ms > self.max_forward_jump_ms:
                raise RuntimeError("SYSTEM_CLOCK_JUMPED_FORWARD")
        self._last_ms = current
        return current


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
    runtime_instance_id: str = ""

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
        if self.runtime_instance_id and not self.runtime_instance_id.strip():
            raise ValueError("runtime_instance_id must be non-empty when supplied")


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
        allocator: CandidateAllocator | None = None,
        strategy_order: tuple[str, ...] = (),
        clock: Clock | None = None,
        event_bus: EventBus | None = None,
        supervisor: RuntimeSupervisor | None = None,
    ) -> None:
        if not controllers:
            raise ValueError("at least one strategy controller is required")
        if config.allow_execution and execution is None:
            raise ValueError("execution sink is required when allow_execution=true")
        self.config = config
        self.market_data = market_data
        self.controllers = controllers
        self.context_factory = context_factory
        self.execution = execution
        self.market_state_factory = market_state_factory
        self.allocator = allocator
        self.strategy_order = strategy_order or tuple(c.strategy_id for c in controllers)
        self.clock = clock or SystemClock()
        self.events = event_bus or EventBus()
        self.supervisor = supervisor or RuntimeSupervisor(
            node_id=config.node_id,
            max_heartbeat_age_ms=max(config.heartbeat_interval_ms * 3, 1_000),
        )
        self._cycle_number = 0
        self.metrics = RuntimeMetrics()
        self.runtime_instance_id = config.runtime_instance_id.strip() or uuid4().hex

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
            return self._cycle_once(now_ms)
        except Exception as exc:
            self.metrics.record_cycle_failure()
            self.supervisor.freeze(f"CYCLE_ERROR:{type(exc).__name__}")
            self.metrics.record_freeze()
            try:
                self.events.publish(
                    FreezeEvent(
                        event_id=self._event_id(f"freeze:{self._cycle_number + 1}"),
                        occurred_at_ms=now_ms,
                        source=self.config.node_id,
                        source_version="node-v2",
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
        decisions: list[tuple[StrategyDecision, object, MarketState]] = []

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
                        event_id=self._event_id(f"quote:{self._cycle_number}:{symbol}"),
                        occurred_at_ms=now_ms,
                        source="trading_node",
                        source_version="node-v2",
                        symbol=symbol,
                        bid=str(quote.bid),
                        ask=str(quote.ask),
                        event_time_ms=quote.event_time_ms,
                        usable_at_ms=quote.event_time_ms,
                    )
                )
                quote_age_ms = now_ms - quote.event_time_ms
                if quote_age_ms < 0:
                    self.supervisor.freeze(f"FUTURE_QUOTE:{symbol}")
                    raise RuntimeError(f"future broker quote:{symbol}")

                bars = self.market_data.completed_bars(
                    symbol=symbol,
                    timeframe=self.config.timeframe,
                    count=self.config.bars_per_symbol,
                )
                market = (
                    self.market_state_factory(quote=quote, now_ms=now_ms)
                    if self.market_state_factory is not None
                    else self._safe_default_market(quote, quote_age_ms)
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
                        event_id=self._event_id(f"forecast:{self._cycle_number}:{symbol}"),
                        occurred_at_ms=now_ms,
                        source=decision.strategy_id,
                        source_version="controller-v2",
                        symbol=symbol,
                        forecast=decision.forecast,
                    )
                )
                self.events.publish(
                    OpportunityEvent(
                        event_id=self._event_id(f"opportunity:{self._cycle_number}:{symbol}"),
                        occurred_at_ms=now_ms,
                        source=decision.strategy_id,
                        source_version="controller-v2",
                        candidate=decision.candidate,
                    )
                )
                decisions.append((decision, quote, market))

        if not decisions:
            self._publish_heartbeat(now_ms)
            return tuple(results)

        candidates = tuple(decision.candidate for decision, _, _ in decisions)
        if len({candidate.candidate_id for candidate in candidates}) != len(candidates):
            raise RuntimeError("duplicate candidate identity in cycle")

        allocation: AllocationResult | None = None
        if self.allocator is not None:
            allocation = self.allocator.allocate(
                candidates=candidates,
                strategy_order=self.strategy_order,
            )
            approved_ids = {candidate.candidate_id for candidate in allocation.approved}
            rejected_reasons = dict(allocation.rejected)
        else:
            approved_ids = {
                candidate.candidate_id
                for candidate in candidates
                if candidate.state == "ADMITTED"
            }
            rejected_reasons = {}

        # Preserve the node's historical cycle result contract: strategy decisions are
        # observable even when execution is disabled or allocation rejects them.
        results.extend(decision for decision, _, _ in decisions)

        decision_by_id = {decision.candidate.candidate_id: (decision, quote, market) for decision, quote, market in decisions}
        for candidate in candidates:
            approved = candidate.candidate_id in approved_ids and candidate.state == "ADMITTED"
            reason = "ALLOCATED" if approved else (
                rejected_reasons.get(candidate.candidate_id, candidate.reason)
            )
            self.metrics.record_strategy_decision(admitted=approved)
            if candidate.state == "ADMITTED" and self.allocator is not None:
                self.events.publish(
                    AllocationDecisionEvent(
                        event_id=self._event_id(f"allocation:{self._cycle_number}:{candidate.candidate_id}"),
                        occurred_at_ms=now_ms,
                        source="strategy_allocator",
                        source_version="allocator-v1",
                        candidate_id=candidate.candidate_id,
                        strategy_id=candidate.strategy_id,
                        symbol=candidate.instrument,
                        approved=approved,
                        reason=reason,
                    )
                )

        for candidate in candidates:
            if candidate.candidate_id not in approved_ids or candidate.state != "ADMITTED":
                continue
            decision, quote, market = decision_by_id[candidate.candidate_id]
            if not self.config.allow_execution:
                continue
            if self.execution is None:
                raise RuntimeError("execution sink missing")
            instrument = self.market_data.instrument_spec(candidate.instrument)
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
            self.metrics.record_execution(
                outcome=getattr(attempt, "broker_outcome", None)
                or getattr(attempt, "decision", None)
            )
            if getattr(attempt, "risk", None) is not None:
                self.events.publish(
                    RiskDecisionEvent(
                        event_id=self._event_id(f"risk:{self._cycle_number}:{candidate.instrument}:{intent.intent_id}"),
                        occurred_at_ms=now_ms,
                        source=self.config.node_id,
                        source_version="risk-engine-v2",
                        symbol=candidate.instrument,
                        intent_id=intent.intent_id,
                        decision=attempt.risk,
                    )
                )
            self.events.publish(
                OrderLifecycleEvent(
                    event_id=self._event_id(f"order:{self._cycle_number}:{candidate.instrument}:{intent.intent_id}"),
                    occurred_at_ms=now_ms,
                    source=self.config.node_id,
                    source_version="execution-boundary-v2",
                    client_order_id=deterministic_client_order_id(intent),
                    order_id=getattr(attempt, "order_id", None),
                    state=getattr(attempt, "order_state", None),
                    broker_order_id=getattr(attempt, "broker_order_id", None),
                    outcome=getattr(attempt, "broker_outcome", None),
                    reasons=tuple(getattr(attempt, "reasons", ())),
                )
            )
            results.append(attempt)

        self._publish_heartbeat(now_ms)
        return tuple(results)

    @staticmethod
    def _safe_default_market(quote, quote_age_ms: int) -> MarketState:
        from packages.models import EventState

        return MarketState(
            EventState.NORMAL,
            quote_age_ms,
            (quote.ask - quote.bid) / quote.mid,
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
        )

    def _event_id(self, suffix: str) -> str:
        suffix = suffix.strip()
        if not suffix:
            raise ValueError("event suffix is required")
        return f"{self.config.node_id}:{self.runtime_instance_id}:{suffix}"

    def _publish_heartbeat(self, now_ms: int) -> None:
        self.supervisor.heartbeat(now_ms)
        health = self.supervisor.health(now_ms)
        self.events.publish(
            HeartbeatEvent(
                event_id=self._event_id(f"heartbeat:{self._cycle_number}"),
                occurred_at_ms=now_ms,
                source=self.config.node_id,
                source_version="node-v2",
                node_id=self.config.node_id,
                state=self.supervisor.state.value,
                health="HEALTHY" if health.healthy else (health.reason or "UNHEALTHY"),
            )
        )

    def run(
        self,
        *,
        max_cycles: int | None = None,
        sleep_seconds: float = 1.0,
        sleep_fn: Callable[[float], None] = sleep,
    ) -> None:
        """Run until stopped/frozen/failed, or until max_cycles is reached."""
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
    "CandidateAllocator",
    "Clock",
    "ExecutionSink",
    "IntentContextFactory",
    "MarketStateFactory",
    "MarketDataFeed",
    "RuntimeConfig",
    "SystemClock",
    "TradingNode",
]
