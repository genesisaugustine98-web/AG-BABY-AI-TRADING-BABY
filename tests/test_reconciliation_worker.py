from dataclasses import dataclass, field
from decimal import Decimal

from apps.reconciliation.worker import ReconciliationWorker
from packages.broker_truth import BrokerPositionTruth, BrokerSnapshot
from packages.execution_ledger import BrokerOrderTruth, InternalOrderTruth


@dataclass
class Truth:
    orders: tuple[InternalOrderTruth, ...] = ()
    positions: tuple[BrokerPositionTruth, ...] = ()
    def active_orders(self): return self.orders
    def positions(self): return self.positions


@dataclass
class FakeAdapter:
    snapshot_value: BrokerSnapshot
    def snapshot(self): return self.snapshot_value


@dataclass
class FakeStore:
    snapshots: list = field(default_factory=list)
    outcomes: list = field(default_factory=list)
    frozen: bool | None = None
    def record_snapshot(self, snapshot): self.snapshots.append(snapshot)
    def record_outcome(self, outcome): self.outcomes.append(outcome)
    def set_frozen(self, frozen): self.frozen = frozen


def test_clean_cycle_unfreezes_only_after_match():
    internal = Truth(
        orders=(InternalOrderTruth("o1", "c1", "USDJPY", "FILLED", Decimal("1")),),
        positions=(BrokerPositionTruth("USDJPY", Decimal("1")),),
    )
    broker = BrokerSnapshot(
        orders=(BrokerOrderTruth("b1", "c1", "USDJPY", "FILLED", Decimal("1")),),
        positions=(BrokerPositionTruth("USDJPY", Decimal("1")),),
        captured_at="2026-09-16T18:00:00+00:00",
    )
    store = FakeStore()
    result = ReconciliationWorker(FakeAdapter(broker), internal, store).run_once()
    assert result.status == "MATCHED"
    assert store.frozen is False
    assert len(store.snapshots) == 1
    assert len(store.outcomes) == 1


def test_drift_freezes():
    internal = Truth(positions=(BrokerPositionTruth("USDJPY", Decimal("1")),))
    broker = BrokerSnapshot(orders=(), positions=(), captured_at="2026-09-16T18:01:00+00:00")
    store = FakeStore()
    result = ReconciliationWorker(FakeAdapter(broker), internal, store).run_once()
    assert result.status == "FREEZE"
    assert store.frozen is True


def test_adapter_failure_never_unfreezes():
    class BrokenAdapter:
        def snapshot(self): raise RuntimeError("broker unavailable")
    store = FakeStore(frozen=True)
    try:
        ReconciliationWorker(BrokenAdapter(), Truth(), store).run_once()
    except RuntimeError:
        pass
    else:
        raise AssertionError("broken broker adapter did not fail")
    assert store.frozen is True
