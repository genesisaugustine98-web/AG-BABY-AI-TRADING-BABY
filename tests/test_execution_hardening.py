from decimal import Decimal
from types import SimpleNamespace

from apps.execution_gateway.mt5_gateway import DemoOnlyMT5Gateway
from integrations.supabase_execution import SupabaseExecutionStore
from packages.execution_ledger import BrokerOrderTruth, InternalOrderTruth, reconcile_order


def test_reconciliation_normalizes_equivalent_state_vocabulary():
    result = reconcile_order(
        InternalOrderTruth("internal-1", "AGDEMO-1", "EURUSD", "ACKNOWLEDGED", Decimal("2")),
        BrokerOrderTruth("broker-1", "AGDEMO-1", "EURUSD", "TRADE_ORDER_STATE_PLACED", Decimal("2")),
    )
    assert result.status == "MATCHED"
    assert result.reasons == ()


def test_mt5_comment_accepts_current_and_legacy_identity_prefixes():
    assert DemoOnlyMT5Gateway._client_order_id("AGDEMO-abc") == "AGDEMO-abc"
    assert DemoOnlyMT5Gateway._client_order_id("AG-legacy") == "AG-legacy"
    assert DemoOnlyMT5Gateway._client_order_id("untrusted-comment") == ""


def test_mt5_state_mapping_uses_canonical_internal_lifecycle():
    fake_mt5 = SimpleNamespace(
        TRADE_ORDER_STATE_STARTED=1,
        TRADE_ORDER_STATE_PLACED=2,
        TRADE_ORDER_STATE_CANCELED=3,
        TRADE_ORDER_STATE_PARTIAL=4,
        TRADE_ORDER_STATE_FILLED=5,
        TRADE_ORDER_STATE_REJECTED=6,
        TRADE_ORDER_STATE_EXPIRED=7,
        TRADE_ORDER_STATE_REQUEST_ADD=8,
        TRADE_ORDER_STATE_REQUEST_MODIFY=9,
        TRADE_ORDER_STATE_REQUEST_CANCEL=10,
    )
    assert DemoOnlyMT5Gateway._state_name(fake_mt5, 2) == "ACCEPTED"
    assert DemoOnlyMT5Gateway._state_name(fake_mt5, 4) == "PARTIAL"
    assert DemoOnlyMT5Gateway._state_name(fake_mt5, 5) == "FILLED"
    assert DemoOnlyMT5Gateway._state_name(fake_mt5, 7) == "CANCELED"


def test_supabase_resolver_scopes_identity_to_environment(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "server-secret")
    store = SupabaseExecutionStore(environment="demo")
    calls = []

    def fake_request(method, table, **kwargs):
        calls.append((method, table, kwargs))
        return [{
            "order_id": "internal-1",
            "client_order_id": "AGDEMO-1",
            "broker_order_id": "123",
            "instrument": "EURUSD",
            "side": "buy",
            "environment": "demo",
            "state": "PARTIALLY_FILLED",
        }]

    store._request = fake_request
    assert store.resolve("123", "EURUSD", "BUY") == "internal-1"
    query = calls[0][2]["query"]
    assert query["environment"] == "eq.demo"
    assert query["broker_order_id"] == "eq.123"
    assert query["instrument"] == "eq.EURUSD"
    assert query["side"] == "eq.buy"


def test_supabase_resolver_refuses_ambiguous_broker_identity(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "server-secret")
    store = SupabaseExecutionStore(environment="demo")
    store._request = lambda *args, **kwargs: [{"order_id": "a", "client_order_id": "AGDEMO-a"}, {"order_id": "b", "client_order_id": "AGDEMO-b"}]
    assert store.resolve("123", "EURUSD", "BUY") is None
