from decimal import Decimal
from types import SimpleNamespace

from apps.execution_gateway.mt5_orders import DemoOnlyMT5OrderAdapter
from packages.demo_execution import SubmissionRequest


class FakeMT5:
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TYPE_BUY_LIMIT = 2
    ORDER_TYPE_SELL_LIMIT = 3
    ORDER_TYPE_BUY_STOP = 4
    ORDER_TYPE_SELL_STOP = 5
    TRADE_ACTION_DEAL = 10
    TRADE_ACTION_PENDING = 11
    TRADE_ACTION_REMOVE = 12
    TRADE_ACTION_MODIFY = 13
    TRADE_RETCODE_DONE = 10009
    ORDER_TIME_GTC = 0
    ORDER_TIME_SPECIFIED = 2
    ORDER_FILLING_RETURN = 2
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    SYMBOL_FILLING_FOK = 1
    SYMBOL_FILLING_IOC = 2
    SYMBOL_TRADE_EXECUTION_MARKET = 2

    def __init__(self):
        self.requests=[]
        self.active=[SimpleNamespace(ticket=555,type=self.ORDER_TYPE_BUY_LIMIT)]

    def symbol_info(self,symbol):
        return SimpleNamespace(visible=True,volume_min=Decimal("0.01"),volume_max=Decimal("10"),volume_step=Decimal("0.01"),
                               filling_mode=self.SYMBOL_FILLING_FOK,trade_exemode=self.SYMBOL_TRADE_EXECUTION_MARKET)

    def symbol_info_tick(self,symbol):
        return SimpleNamespace(time=1789824759,bid=150.0,ask=150.002)

    def order_check(self,request):
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE)

    def order_send(self,request):
        self.requests.append(request)
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE,order=555)

    def orders_get(self):
        return list(self.active)

    def symbol_select(self,symbol,selected):
        return True

    def last_error(self):
        return (0,"ok")


def test_pending_request_carries_expiration(monkeypatch):
    monkeypatch.setenv("EXECUTION_ENV","demo")
    mt5=FakeMT5()
    req=SubmissionRequest("AGDEMO-E","i1","EURUSD","BUY",Decimal("0.1"),"LIMIT",Decimal("149.5"),Decimal("149"),Decimal("152"),1789824769000)
    result=DemoOnlyMT5OrderAdapter(mt5).submit(req)
    assert result.outcome=="ACCEPTED"
    sent=mt5.requests[0]
    assert sent["type_time"]==mt5.ORDER_TIME_SPECIFIED
    assert sent["expiration"]==1789824769


def test_replace_checks_active_pending_order_and_sends_modify(monkeypatch):
    monkeypatch.setenv("EXECUTION_ENV","demo")
    mt5=FakeMT5()
    result=DemoOnlyMT5OrderAdapter(mt5).replace(
        "555",symbol="EURUSD",side="BUY",limit_price=Decimal("149.8"),
        stop_price=Decimal("149.0"),target_price=Decimal("152.0"),expires_at_ms=1789824769000,
    )
    assert result.outcome=="ACCEPTED"
    sent=mt5.requests[0]
    assert sent["action"]==mt5.TRADE_ACTION_MODIFY
    assert sent["order"]==555
    assert sent["price"]==149.8
    assert sent["expiration"]==1789824769


def test_replace_fails_closed_when_order_is_not_active(monkeypatch):
    monkeypatch.setenv("EXECUTION_ENV","demo")
    mt5=FakeMT5()
    mt5.active=[]
    result=DemoOnlyMT5OrderAdapter(mt5).replace(
        "555",symbol="EURUSD",side="BUY",limit_price=Decimal("149.8"),
        stop_price=None,target_price=None,
    )
    assert result.outcome=="UNKNOWN"
    assert result.reason=="ACTIVE_ORDER_NOT_FOUND"
