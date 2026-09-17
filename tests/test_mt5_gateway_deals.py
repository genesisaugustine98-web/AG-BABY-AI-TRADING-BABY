from types import SimpleNamespace

import pytest

from apps.execution_gateway.mt5_gateway import DemoOnlyMT5Gateway


class FakeMT5:
    DEAL_TYPE_BUY = 0
    DEAL_TYPE_SELL = 1

    def history_deals_get(self, date_from, date_to, **kwargs):
        return [
            SimpleNamespace(
                ticket=11,
                order=22,
                time=1,
                time_msc=1000,
                type=0,
                entry=0,
                position_id=33,
                volume=1,
                price=150,
                commission=0,
                swap=0,
                profit=0,
                fee=0,
                reason=3,
                magic=7,
                symbol="USDJPY",
                comment="AG-1",
                external_id="",
            )
        ]

    def last_error(self):
        return (0, "ok")


def test_confirmed_deals_requires_connected_gateway(monkeypatch):
    monkeypatch.setenv("EXECUTION_ENV", "demo")
    gateway = DemoOnlyMT5Gateway()
    with pytest.raises(RuntimeError, match="not connected"):
        gateway.confirmed_deals("from", "to")


def test_confirmed_deals_reuses_connected_mt5_session(monkeypatch):
    monkeypatch.setenv("EXECUTION_ENV", "demo")
    gateway = DemoOnlyMT5Gateway()
    fake = FakeMT5()
    monkeypatch.setattr(gateway, "_import", lambda: fake)
    gateway.connected = True

    records = gateway.confirmed_deals("from", "to", group="*USDJPY*")
    assert len(records) == 1
    assert records[0].broker_fill_id == "11"
    assert records[0].broker_order_id == "22"
