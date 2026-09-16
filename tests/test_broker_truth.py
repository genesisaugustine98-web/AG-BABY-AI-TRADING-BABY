from decimal import Decimal

from packages.broker_truth import (
    BrokerPositionTruth,
    BrokerSnapshot,
    Reconciler,
)
from packages.execution_ledger import BrokerOrderTruth, InternalOrderTruth


def snap(orders=(), positions=()):
    return BrokerSnapshot(tuple(orders), tuple(positions), "2026-09-16T18:00:00+00:00")


def test_clean_snapshot_is_matched():
    internal_orders = (InternalOrderTruth("o1", "c1", "USDJPY", "FILLED", Decimal("2")),)
    internal_positions = (BrokerPositionTruth("USDJPY", Decimal("2")),)
    broker_orders = (BrokerOrderTruth("b1", "c1", "USDJPY", "FILLED", Decimal("2")),)
    broker_positions = (BrokerPositionTruth("USDJPY", Decimal("2")),)
    out = Reconciler().reconcile(internal_orders, internal_positions, snap(broker_orders, broker_positions))
    assert out.status == "MATCHED"
    assert out.freeze_required is False


def test_missing_broker_order_forces_freeze():
    internal_orders = (InternalOrderTruth("o1", "c1", "USDJPY", "SUBMITTED", Decimal("0")),)
    out = Reconciler().reconcile(internal_orders, (), snap())
    assert out.status == "FREEZE"
    assert out.freeze_required is True
    assert out.results[0].status == "UNKNOWN"


def test_position_drift_forces_freeze():
    internal_positions = (BrokerPositionTruth("USDJPY", Decimal("2")),)
    broker_positions = (BrokerPositionTruth("USDJPY", Decimal("1")),)
    out = Reconciler().reconcile((), internal_positions, snap(positions=broker_positions))
    assert out.status == "FREEZE"
    assert out.position_drift == ("position_mismatch:USDJPY",)


def test_unexpected_extra_broker_position_forces_freeze():
    broker_positions = (BrokerPositionTruth("EURUSD", Decimal("1")),)
    out = Reconciler().reconcile((), (), snap(positions=broker_positions))
    assert out.status == "FREEZE"
    assert out.position_drift == ("position_mismatch:EURUSD",)
