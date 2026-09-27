from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.execution_gateway.mt5_orders import DemoOnlyMT5OrderAdapter
from packages.demo_execution import SubmissionRequest


class FakeMT5:
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TYPE_BUY_LIMIT = 2
    ORDER_TYPE_SELL_LIMIT = 3
    TRADE_ACTION_DEAL = 10
    TRADE_ACTION_PENDING = 11
    TRADE_ACTION_REMOVE = 12
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_PLACED = 10008
    TRADE_RETCODE_DONE_PARTIAL = 10010
    ORDER_TIME_GTC = 0
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2
    SYMBOL_FILLING_FOK = 1
    SYMBOL_FILLING_IOC = 2
    SYMBOL_TRADE_EXECUTION_MARKET = 2

    def __init__(self, retcode=TRADE_RETCODE_DONE):
        self.retcode = retcode
        self.requests = []

    def symbol_info(self, symbol):
        return SimpleNamespace(
            visible=True,
            volume_min=0.01,
            volume_max=10.0,
            volume_step=0.01,
            filling_mode=self.SYMBOL_FILLING_FOK,
            trade_exemode=self.SYMBOL_TRADE_EXECUTION_MARKET,
        )

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(time=1789824759, bid=150.0, ask=150.002)

    def order_check(self, request):
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE)

    def order_send(self, request):
        self.requests.append(request)
        return SimpleNamespace(retcode=self.retcode, order=555)

    def orders_get(self):
        return []

    def history_orders_get(self):
        return []

    def last_error(self):
        return (0, "ok")

    def symbol_select(self, symbol, selected):
        return True


def req():
    return SubmissionRequest("AGDEMO-123", "i1", "USDJPY", "BUY", Decimal("0.10"), "MARKET", None, Decimal("149.0"), Decimal("152.0"))


def test_demo_order_uses_order_check_then_order_send(monkeypatch):
    monkeypatch.setenv("EXECUTION_ENV", "demo")
    mt5 = FakeMT5()
    result = DemoOnlyMT5OrderAdapter(mt5).submit(req())
    assert result.outcome == "ACCEPTED"
    assert result.broker_order_id == "555"
    sent = mt5.requests[0]
    assert isinstance(sent, dict)
    assert sent["comment"] == "AGDEMO-123"
    assert sent["volume"] == 0.1
    assert sent["sl"] == 149.0
    assert sent["tp"] == 152.0


def test_demo_order_rejects_wrong_stop(monkeypatch):
    monkeypatch.setenv("EXECUTION_ENV", "demo")
    bad = SubmissionRequest("AGDEMO-123", "i1", "USDJPY", "BUY", Decimal("0.10"), "MARKET", None, Decimal("151.0"), Decimal("152.0"))
    with pytest.raises(ValueError, match="stop"):
        DemoOnlyMT5OrderAdapter(FakeMT5()).submit(bad)


def test_demo_order_refuses_live(monkeypatch):
    monkeypatch.setenv("EXECUTION_ENV", "live")
    with pytest.raises(RuntimeError, match="demo-only"):
        DemoOnlyMT5OrderAdapter(FakeMT5())


def test_demo_order_rejects_zero_tick(monkeypatch):
    monkeypatch.setenv("EXECUTION_ENV", "demo")
    mt5 = FakeMT5()
    mt5.symbol_info_tick = lambda symbol: SimpleNamespace(time=0, bid=0.0, ask=0.0)
    with pytest.raises(RuntimeError, match="invalid_or_stale_symbol_tick"):
        DemoOnlyMT5OrderAdapter(mt5).submit(req())


def test_demo_order_rejects_unaligned_volume_instead_of_silently_rounding():
    with pytest.raises(ValueError, match="aligned"):
        DemoOnlyMT5OrderAdapter._step_volume(
            Decimal("0.07"), Decimal("0.03"), Decimal("1.0"), Decimal("0.05")
        )
    assert DemoOnlyMT5OrderAdapter._step_volume(
        Decimal("0.08"), Decimal("0.03"), Decimal("1.0"), Decimal("0.05")
    ) == Decimal("0.08")


def test_pending_order_forces_return_filling_policy(monkeypatch):
    monkeypatch.setenv("EXECUTION_ENV", "demo")
    mt5 = FakeMT5()
    pending = SubmissionRequest(
        "AGDEMO-123", "i1", "USDJPY", "BUY", Decimal("0.10"),
        "LIMIT", Decimal("149.5"), Decimal("149.0"), Decimal("152.0")
    )
    result = DemoOnlyMT5OrderAdapter(mt5).submit(pending)
    assert result.outcome == "ACCEPTED"
    assert mt5.requests[0]["type_filling"] == mt5.ORDER_FILLING_RETURN
    assert mt5.requests[0]["action"] == mt5.TRADE_ACTION_PENDING
