from decimal import Decimal

from packages.broker_truth import BrokerPositionTruth, BrokerSnapshot, ReconciliationOutcome
from packages.execution_ledger import BrokerOrderTruth
from packages.reconciliation_guard import guarded_outcome, validate_snapshot


def test_duplicate_broker_client_order_ids_are_ambiguous():
    snapshot = BrokerSnapshot(
        orders=(
            BrokerOrderTruth("b1", "c1", "USDJPY", "FILLED", Decimal("1")),
            BrokerOrderTruth("b2", "c1", "USDJPY", "FILLED", Decimal("2")),
        ),
        positions=(),
        captured_at="2026-09-16T20:00:00+00:00",
    )
    result = validate_snapshot(snapshot)
    assert result.valid is False
    assert "duplicate_broker_client_order_id:c1" in result.reasons


def test_duplicate_position_rows_are_ambiguous():
    snapshot = BrokerSnapshot(
        orders=(),
        positions=(
            BrokerPositionTruth("USDJPY", Decimal("1")),
            BrokerPositionTruth("USDJPY", Decimal("1")),
        ),
        captured_at="2026-09-16T20:00:00+00:00",
    )
    result = validate_snapshot(snapshot)
    assert result.valid is False
    assert "duplicate_broker_position_instrument:USDJPY" in result.reasons


def test_negative_broker_fill_quantity_forces_freeze():
    snapshot = BrokerSnapshot(
        orders=(BrokerOrderTruth("b1", "c1", "USDJPY", "FILLED", Decimal("-1")),),
        positions=(),
        captured_at="2026-09-16T20:00:00+00:00",
    )
    result = validate_snapshot(snapshot)
    assert result.valid is False
    assert "negative_broker_filled_quantity:b1" in result.reasons


def test_guarded_outcome_converts_structural_ambiguity_to_freeze():
    snapshot = BrokerSnapshot(
        orders=(
            BrokerOrderTruth("b1", "c1", "USDJPY", "FILLED", Decimal("1")),
            BrokerOrderTruth("b2", "c1", "USDJPY", "FILLED", Decimal("1")),
        ),
        positions=(),
        captured_at="2026-09-16T20:00:00+00:00",
    )
    clean = ReconciliationOutcome("MATCHED", False, (), ())
    guarded = guarded_outcome(snapshot, clean)
    assert guarded.status == "FREEZE"
    assert guarded.freeze_required is True
    assert "duplicate_broker_client_order_id:c1" in guarded.position_drift
