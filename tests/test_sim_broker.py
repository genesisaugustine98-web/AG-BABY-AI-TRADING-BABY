from decimal import Decimal

from apps.execution_gateway.sim_broker import SimBroker


def test_duplicate_client_order_id_returns_same_order():
    broker = SimBroker()
    first = broker.submit("client-1", "USDJPY", "BUY", Decimal("1"), Decimal("150.00"))
    second = broker.submit("client-1", "USDJPY", "BUY", Decimal("1"), Decimal("150.00"))

    assert first.broker_id == second.broker_id
    assert second.filled_quantity == Decimal("1")
    assert len(broker.snapshot()) == 1


def test_client_order_lookup_is_truthful():
    broker = SimBroker()
    order = broker.submit("client-2", "EURUSD", "SELL", Decimal("2"), Decimal("1.10"))

    found = broker.lookup_by_client_order_id("client-2")
    assert found is order
    assert broker.lookup_by_client_order_id("missing") is None
