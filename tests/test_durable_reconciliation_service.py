from decimal import Decimal

import pytest

from apps.reconciliation.service import DurableReconciliationService
from apps.reconciliation.worker import ReconciliationWorker
from packages.broker_truth import BrokerPositionTruth, BrokerSnapshot
from packages.execution_ledger import InternalOrderTruth
from packages.recovery import RecoveryState


class Adapter:
    def __init__(self, snapshot=None, error=None):
        self._snapshot = snapshot
        self._error = error

    def snapshot(self):
        if self._error:
            raise self._error
        return self._snapshot


class Store:
    def __init__(self, frozen=False):
        self.frozen = frozen
        self.frozen_reasons = []
        self.snapshots = []
        self.outcomes = []

    def active_orders(self):
        return (InternalOrderTruth("o1", "AG-1", "USDJPY", "ACCEPTED", Decimal("1")),)

    def positions(self):
        return (BrokerPositionTruth("USDJPY", Decimal("1")),)

    def record_snapshot(self, snapshot):
        self.snapshots.append(snapshot)

    def record_outcome(self, outcome):
        self.outcomes.append(outcome)

    def load_frozen(self):
        return self.frozen

    def set_frozen(self, frozen, reason=None):
        self.frozen = frozen
        self.frozen_reasons.append(reason)


def clean_snapshot():
    return BrokerSnapshot(
        orders=(),
        positions=(BrokerPositionTruth("USDJPY", Decimal("1")),),
        captured_at="2026-09-16T19:00:00+00:00",
    )


def test_startup_never_allows_trading_before_reconciliation():
    store = Store(frozen=False)
    worker = ReconciliationWorker(Adapter(clean_snapshot()), store, store)
    service = DurableReconciliationService(worker)
    result = service.startup()
    assert result.state == RecoveryState.RECONCILING
    assert service.trading_permitted is False


def test_clean_reconciliation_opens_execution():
    store = Store(frozen=False)
    worker = ReconciliationWorker(Adapter(clean_snapshot()), store, store)
    service = DurableReconciliationService(worker)
    service.startup()
    result = service.reconcile_once()
    assert result.status == "MATCHED"
    assert service.trading_permitted is True
    assert store.frozen is False


def test_reconciliation_error_persists_freeze_and_stays_closed():
    store = Store(frozen=False)
    worker = ReconciliationWorker(Adapter(error=RuntimeError("broker unavailable")), store, store)
    service = DurableReconciliationService(worker)
    service.startup()
    with pytest.raises(RuntimeError):
        service.reconcile_once()
    assert store.frozen is True
    assert service.trading_permitted is False
    assert store.frozen_reasons[-1] == "reconciliation_exception:RuntimeError"


def test_drift_cannot_reopen_execution():
    store = Store(frozen=True)
    drifted = BrokerSnapshot(
        orders=(),
        positions=(BrokerPositionTruth("USDJPY", Decimal("2")),),
        captured_at="2026-09-16T19:01:00+00:00",
    )
    worker = ReconciliationWorker(Adapter(drifted), store, store)
    service = DurableReconciliationService(worker)
    service.startup()
    result = service.reconcile_once()
    assert result.status == "FREEZE"
    assert service.trading_permitted is False
    assert store.frozen is True
