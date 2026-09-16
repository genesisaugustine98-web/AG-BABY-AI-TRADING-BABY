"""Crash-safe reconciliation worker orchestration.

This worker deliberately depends on interfaces rather than a specific broker or database.
The production deployment can bind these interfaces to MT5 and Supabase without weakening
fail-closed behavior.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from packages.broker_truth import BrokerPositionTruth, BrokerSnapshot, BrokerTruthAdapter, ReconciliationOutcome, Reconciler
from packages.execution_ledger import InternalOrderTruth


class InternalTruthStore(Protocol):
    def active_orders(self) -> tuple[InternalOrderTruth, ...]: ...
    def positions(self) -> tuple[BrokerPositionTruth, ...]: ...


class ReconciliationStore(Protocol):
    def record_snapshot(self, snapshot: BrokerSnapshot) -> None: ...
    def record_outcome(self, outcome: ReconciliationOutcome) -> None: ...
    def load_frozen(self) -> bool: ...
    def set_frozen(self, frozen: bool, reason: str | None = None) -> None: ...


@dataclass(frozen=True)
class WorkerResult:
    captured_at: str
    status: str
    freeze_required: bool


class ReconciliationWorker:
    def __init__(self, adapter: BrokerTruthAdapter, truth_store: InternalTruthStore, store: ReconciliationStore):
        self.adapter = adapter
        self.truth_store = truth_store
        self.store = store
        self.reconciler = Reconciler()

    def run_once(self) -> WorkerResult:
        snapshot = self.adapter.snapshot()
        self.store.record_snapshot(snapshot)
        outcome = self.reconciler.reconcile(
            self.truth_store.active_orders(),
            self.truth_store.positions(),
            snapshot,
        )
        self.store.record_outcome(outcome)
        # Only a clean reconciliation can unfreeze. Exceptions before this point leave
        # the persisted state untouched; the durable service freezes on error.
        self.store.set_frozen(outcome.freeze_required)
        return WorkerResult(snapshot.captured_at, outcome.status, outcome.freeze_required)
