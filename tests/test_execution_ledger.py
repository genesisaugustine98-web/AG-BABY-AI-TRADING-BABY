from datetime import datetime, timezone
from decimal import Decimal

from packages.execution_ledger import (
    AppendOnlyLedger,
    BrokerOrderTruth,
    InternalOrderTruth,
    reconcile_missing_broker_order,
    reconcile_order,
)


def test_hash_chain_is_reproducible_and_verifiable():
    ledger = AppendOnlyLedger()
    ts = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    first = ledger.append(
        event_id="e1",
        event_type="ORDER_INTENT",
        correlation_id="c1",
        payload={"symbol": "USDJPY", "qty": "1"},
        occurred_at=ts,
    )
    ledger.append(
        event_id="e2",
        event_type="ORDER_STATE",
        correlation_id="c1",
        payload={"state": "UNKNOWN"},
        occurred_at=ts,
    )
    assert first.previous_event_hash is None
    assert ledger.events[1].previous_event_hash == first.event_hash
    assert ledger.verify_chain()


def test_duplicate_event_id_is_rejected():
    ledger = AppendOnlyLedger()
    ledger.append(event_id="e1", event_type="X", correlation_id="c1", payload={})
    try:
        ledger.append(event_id="e1", event_type="Y", correlation_id="c1", payload={})
    except ValueError as exc:
        assert "duplicate event_id" in str(exc)
    else:
        raise AssertionError("duplicate event id was accepted")


def test_matching_broker_truth_is_matched():
    internal = InternalOrderTruth("o1", "c1", "USDJPY", "FILLED", Decimal("2"))
    broker = BrokerOrderTruth("b1", "c1", "USDJPY", "FILLED", Decimal("2"))
    result = reconcile_order(internal, broker)
    assert result.status == "MATCHED"
    assert result.drift_count == 0


def test_drift_is_explicit():
    internal = InternalOrderTruth("o1", "c1", "USDJPY", "FILLED", Decimal("2"))
    broker = BrokerOrderTruth("b1", "c1", "USDJPY", "PARTIAL", Decimal("1"))
    result = reconcile_order(internal, broker)
    assert result.status == "DRIFT"
    assert set(result.reasons) == {"state_mismatch", "filled_quantity_mismatch"}


def test_missing_broker_truth_is_unknown():
    internal = InternalOrderTruth("o1", "c1", "USDJPY", "SUBMITTED", Decimal("0"))
    result = reconcile_missing_broker_order(internal)
    assert result.status == "UNKNOWN"
    assert result.reasons == ("broker_order_not_found",)
