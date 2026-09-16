from datetime import datetime, timezone
from decimal import Decimal

from integrations.supabase_accounting import SupabaseAccountingBridge
from packages.accounting import BrokerConfirmedFill


class FakeBridge(SupabaseAccountingBridge):
    def __init__(self, response):
        self.response = response
        self.calls = []

    def _rpc(self, function, payload):
        self.calls.append((function, payload))
        return self.response


def fill():
    return BrokerConfirmedFill(
        fill_id="fill-1",
        broker_order_id="broker-1",
        client_order_id="client-1",
        instrument="USDJPY",
        side="BUY",
        quantity=Decimal("1.25"),
        price=Decimal("150.10"),
        occurred_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
        broker="demo",
    )


def test_bridge_requires_internal_order_id():
    bridge = FakeBridge([{
        "duplicate": False, "position_id": "demo:USDJPY", "instrument": "USDJPY",
        "net_quantity": "1.25", "average_price": "150.10", "realized_pnl": "0",
        "financing_pnl": "0", "state": "OPEN",
    }])
    try:
        bridge.apply(environment="demo", order_id="", fill=fill())
    except ValueError as exc:
        assert str(exc) == "internal order_id is required"
    else:
        raise AssertionError("missing internal order_id must fail closed")


def test_bridge_maps_internal_order_id_and_decimal_payload():
    bridge = FakeBridge([{
        "duplicate": False, "position_id": "demo:USDJPY", "instrument": "USDJPY",
        "net_quantity": "1.25", "average_price": "150.10", "realized_pnl": "0",
        "financing_pnl": "0", "state": "OPEN",
    }])
    result = bridge.apply(environment="demo", order_id="internal-1", fill=fill())
    function, payload = bridge.calls[0]
    assert function == "apply_broker_confirmed_fill"
    assert payload["p_order_id"] == "internal-1"
    assert payload["p_quantity"] == "1.25"
    assert payload["p_price"] == "150.10"
    assert result.net_quantity == Decimal("1.25")
    assert result.average_price == Decimal("150.10")
