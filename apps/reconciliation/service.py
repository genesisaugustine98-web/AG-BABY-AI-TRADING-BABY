"""Durable reconciliation service: startup is never immediately tradable."""
from __future__ import annotations

from dataclasses import dataclass

from packages.recovery import RecoveryController, RecoveryState
from .worker import ReconciliationWorker, WorkerResult


@dataclass(frozen=True)
class StartupResult:
    recovered_frozen: bool
    state: RecoveryState


class DurableReconciliationService:
    """Binds persistent control state to broker reconciliation and recovery.

    A process restart always starts non-tradable. Only a fresh clean broker
    reconciliation moves the controller to READY. Unexpected reconciliation errors
    persist a freeze so a later restart cannot accidentally reopen execution.
    """

    def __init__(self, worker: ReconciliationWorker):
        self.worker = worker
        self.recovery = RecoveryController()

    def startup(self) -> StartupResult:
        persisted_frozen = self.worker.store.load_frozen()
        state = self.recovery.hydrate(persisted_frozen)
        return StartupResult(persisted_frozen, state)

    def reconcile_once(self) -> WorkerResult:
        self.recovery.broker_snapshot_received()
        try:
            result = self.worker.run_once()
        except Exception as exc:
            self.worker.store.set_frozen(True, reason=f"reconciliation_exception:{type(exc).__name__}")
            self.recovery.hydrate(True)
            raise
        self.recovery.reconciliation_result(result.status == "MATCHED")
        return result

    @property
    def trading_permitted(self) -> bool:
        return self.recovery.trading_permitted
