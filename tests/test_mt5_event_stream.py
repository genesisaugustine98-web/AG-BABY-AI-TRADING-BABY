from apps.execution_gateway.mt5_fills import DealHistoryCursor
from apps.execution_gateway.mt5_event_stream import MT5BrokerOrderEventStream
from types import SimpleNamespace


class FakeMT5:
    def __init__(self):
        self.orders=[SimpleNamespace(ticket=1,comment="AGDEMO-1",symbol="EURUSD",state="PLACED",type="BUY_LIMIT",
                                     time_update_msc=1789824760000,volume_current=1,price_open=1.1,sl=1.0,tp=1.2)]
    def orders_get(self): return self.orders
    def history_orders_get(self,start,end): return self.orders
    def last_error(self): return (0,"ok")


class Checkpoint:
    def __init__(self): self.cursor=DealHistoryCursor(); self.saved=[]
    def load_ingestion_checkpoint(self,**kwargs): return self.cursor
    def save_ingestion_checkpoint(self,**kwargs): self.cursor=kwargs["cursor"]; self.saved.append(kwargs)


def test_event_stream_deduplicates_active_history_overlap(monkeypatch):
    monkeypatch.setenv("EXECUTION_ENV","demo")
    cp=Checkpoint()
    stream=MT5BrokerOrderEventStream(FakeMT5(),checkpoint_store=cp)
    first=stream.poll(now_msc=1789824765000)
    second=stream.poll(now_msc=1789824770000)
    assert len(first)==1
    assert second==()
    assert cp.saved[-1]["metadata"]["events"]==0


def test_event_stream_fails_closed_outside_demo(monkeypatch):
    monkeypatch.setenv("EXECUTION_ENV","paper")
    try:
        MT5BrokerOrderEventStream(FakeMT5())
    except RuntimeError as exc:
        assert "demo-only" in str(exc)
    else:
        raise AssertionError("expected demo-only guard")
