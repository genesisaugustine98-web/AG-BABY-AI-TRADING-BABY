"""Trusted-server composition root for the demo execution path."""
from __future__ import annotations

from dataclasses import dataclass

from packages.execution_kernel import ExecutionAttempt, ExecutionKernel
from packages.models import AdmissionContext, InstrumentSpec, TradeIntent
from .mt5_gateway import DemoOnlyMT5Gateway
from .mt5_orders import DemoOnlyMT5OrderAdapter
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

    @classmethod
    def create(cls) -> "DemoExecutionRuntime":
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
            kernel=ExecutionKernel(environment="demo"),
            reconciliation=reconciliation,
        )

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
