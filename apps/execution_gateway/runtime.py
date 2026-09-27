"""Trusted-server composition root for the demo execution path."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from packages.execution_kernel import ExecutionAttempt, ExecutionKernel
from packages.risk_engine import DeterministicRiskEngine, RiskLimits
from packages.models import AdmissionContext, InstrumentSpec, TradeIntent
from .mt5_gateway import DemoOnlyMT5Gateway
from .mt5_orders import DemoOnlyMT5OrderAdapter
from .order_controls import ControlResult, DemoOrderControls, ReplaceRequest
from .mt5_event_stream import MT5BrokerOrderEventStream
from integrations.supabase_order_store import SupabaseOrderStore
from integrations.supabase_execution_store import SupabaseExecutionStore as SafetyStore
from apps.reconciliation.service import DurableReconciliationService
from apps.reconciliation.worker import ReconciliationWorker


@dataclass
class DemoExecutionRuntime:
    """Binds policy/risk -> durable order -> MT5 demo submission.

    The runtime opens only after the durable control state says execution is unfrozen.
    Broker-confirmed fills are still ingested by the separate MT5 deal worker.
    """

    gateway: DemoOnlyMT5Gateway
    orders: SupabaseOrderStore
    safety: SafetyStore
    kernel: ExecutionKernel
    reconciliation: DurableReconciliationService
    event_stream: MT5BrokerOrderEventStream | None = None

    @classmethod
    def create(cls, *, risk_limits: RiskLimits | None = None) -> "DemoExecutionRuntime":
        gateway = DemoOnlyMT5Gateway()
        gateway.connect_and_verify_demo()
        orders = SupabaseOrderStore(environment="demo")
        safety = SafetyStore(environment="demo")
        reconciliation = DurableReconciliationService(
            ReconciliationWorker(gateway, safety, safety)
        )
        try:
            reconciliation.startup()
            reconciliation.reconcile_once()
        except Exception:
            gateway.shutdown()
            raise
        return cls(
            gateway=gateway,
            orders=orders,
            safety=safety,
            kernel=ExecutionKernel(
                environment="demo",
                risk_engine=DeterministicRiskEngine(risk_limits or RiskLimits()),
            ),
            reconciliation=reconciliation,
            event_stream=MT5BrokerOrderEventStream(gateway.mt5_api(), checkpoint_store=safety),
        )

    def poll_broker_events(self, *, now_msc: int) -> tuple:
        stream = self.event_stream
        if stream is None:
            stream = MT5BrokerOrderEventStream(self.gateway.mt5_api(), checkpoint_store=self.safety)
            self.event_stream = stream
        return stream.poll(now_msc=now_msc)

    def submit(self, *, intent: TradeIntent, context: AdmissionContext, instrument: InstrumentSpec) -> ExecutionAttempt:
        from packages.demo_execution import deterministic_client_order_id
        client_order_id = deterministic_client_order_id(intent)
        if self.safety.load_frozen():
            return ExecutionAttempt(
                "DENIED_FROZEN_CONTROL_STATE",
                client_order_id,
                None,
                None,
                None,
                ("EXECUTION_CONTROL_STATE_FROZEN",),
            )
        try:
            # Fresh broker truth is required immediately before every submission. A
            # process can survive between cycles while the broker/session changes underneath it.
            reconciliation = self.reconciliation.reconcile_once()
        except Exception as exc:
            return ExecutionAttempt(
                "DENIED_RECONCILIATION_FAILED",
                client_order_id,
                None,
                None,
                None,
                (f"RECONCILIATION_EXCEPTION:{type(exc).__name__}",),
            )
        if reconciliation.freeze_required or not self.reconciliation.trading_permitted:
            return ExecutionAttempt(
                "DENIED_RECONCILIATION_NOT_READY",
                client_order_id,
                None,
                None,
                None,
                ("FRESH_CLEAN_BROKER_RECONCILIATION_REQUIRED",),
            )
        broker = DemoOnlyMT5OrderAdapter(self.gateway._import())
        return self.kernel.execute(
            intent=intent,
            context=context,
            instrument=instrument,
            repository=self.orders,
            broker=broker,
        )

    def replace_order(
        self,
        *,
        order_id: str,
        limit_price: Decimal,
        stop_price: Decimal | None = None,
        target_price: Decimal | None = None,
        expires_at_ms: int = 0,
    ) -> ControlResult:
        try:
            reconciliation = self.reconciliation.reconcile_once()
        except Exception as exc:
            return ControlResult(False, None, (f"RECONCILIATION_EXCEPTION:{type(exc).__name__}",))
        if reconciliation.freeze_required or not self.reconciliation.trading_permitted:
            return ControlResult(False, None, ("RECONCILIATION_NOT_READY",))
        order = self.orders.get(order_id)
        return DemoOrderControls(self.orders, DemoOnlyMT5OrderAdapter(self.gateway._import())).replace(
            order_id,
            ReplaceRequest(
                symbol=order.instrument,
                side=order.side,
                limit_price=limit_price,
                stop_price=stop_price,
                target_price=target_price,
                expires_at_ms=expires_at_ms,
            ),
        )

    def expire_order(self, *, order_id: str) -> ControlResult:
        try:
            reconciliation = self.reconciliation.reconcile_once()
        except Exception as exc:
            return ControlResult(False, None, (f"RECONCILIATION_EXCEPTION:{type(exc).__name__}",))
        if reconciliation.freeze_required or not self.reconciliation.trading_permitted:
            return ControlResult(False, None, ("RECONCILIATION_NOT_READY",))
        return DemoOrderControls(self.orders, DemoOnlyMT5OrderAdapter(self.gateway._import())).expire(order_id)

    def cancel_order(self, *, order_id: str) -> ControlResult:
        # Cancellation is truth-first too: establish current broker state before mutating it.
        try:
            reconciliation = self.reconciliation.reconcile_once()
        except Exception as exc:
            return ControlResult(False, None, (f"RECONCILIATION_EXCEPTION:{type(exc).__name__}",))
        if reconciliation.freeze_required or not self.reconciliation.trading_permitted:
            return ControlResult(False, None, ("RECONCILIATION_NOT_READY",))
        broker = DemoOnlyMT5OrderAdapter(self.gateway._import())
        return DemoOrderControls(self.orders, broker).cancel(order_id)

    def recover(self, *, order_id: str, client_order_id: str):
        broker = DemoOnlyMT5OrderAdapter(self.gateway._import())
        return self.kernel.recover_unknown(
            order_id=order_id,
            client_order_id=client_order_id,
            repository=self.orders,
            truth=broker,
        )

    def close(self) -> None:
        self.gateway.shutdown()


__all__ = ["DemoExecutionRuntime"]
