from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.execution_gateway.mt5_fills import DealHistoryCursor, MT5DealCollector, MT5FillIngestionService
from integrations.supabase_execution import SupabaseExecutionStore


class FakeMT5:
    DEAL_TYPE_BUY = 0
    DEAL_TYPE_SELL = 1

    def __init__(self, deals=None, error=None):
        self.deals = deals
        self.error = error
        self.calls = []

    def history_deals_get(self, date_from, date_to, **kwargs):
        self.calls.append((date_from, date_to, kwargs))
        if self.error:
            return None
        return self.deals

    def last_error(self):
        return self.error or (0, "ok")


def deal(**overrides):
    values = {
        "ticket": 101,
        "order": 202,
        "time": 1789628400,
        "time_msc": 1789628400123,
        "type": 0,
        "entry": 0,
        "position_id": 303,
        "volume": 1.25,
        "price": 150.125,
        "commission": -0.10,
        "swap": -0.02,
        "profit": 0.0,
        "fee": 0.0,
        "reason": 3,
        "magic": 777,
        "symbol": "USDJPY",
        "comment": "AG-CLIENT-1",
        "external_id": "ext-1",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_trade_deal_becomes_normalized_broker_record(monkeypatch):
    monkeypatch.setenv("EXECUTION_ENV", "demo")
    mt5 = FakeMT5([deal()])
    collector = MT5DealCollector(mt5)
    records = collector.collect("from", "to", group="*USDJPY*")

    assert len(records) == 1
    record = records[0]
    assert record.broker_fill_id == "101"
    assert record.broker_order_id == "202"
    assert record.instrument == "USDJPY"
    assert record.side == "BUY"
    assert str(record.quantity) == "1.25"
    assert str(record.price) == "150.125"
    assert record.commission == Decimal("-0.10")
    assert record.financing == Decimal("-0.02")
    assert record.metadata["entry"] == "IN"
    assert record.metadata["position_id"] == "303"
    assert mt5.calls == [("from", "to", {"group": "*USDJPY*"})]


def test_deal_can_only_become_canonical_fill_after_explicit_internal_binding(monkeypatch):
    monkeypatch.setenv("EXECUTION_ENV", "demo")
    record = MT5DealCollector(FakeMT5([deal()])).collect("from", "to")[0]
    canonical = record.bind_internal_order("internal-order-1")

    assert canonical.order_id == "internal-order-1"
    assert canonical.broker_order_id == "202"
    assert canonical.broker_fill_id == "101"
    assert canonical.fill_id == "mt5:101"
    assert canonical.metadata["order_id_resolution"] == "explicit_internal_order_binding"


def test_ingestion_service_leaves_unresolved_deals_out_of_canonical_sink(monkeypatch):
    monkeypatch.setenv("EXECUTION_ENV", "demo")
    collector = MT5DealCollector(FakeMT5([deal(), deal(ticket=102, order=204)]))

    class Resolver:
        def resolve(self, broker_order_id, instrument, side):
            return "internal-order-1" if broker_order_id == "202" else None

    class Sink:
        def __init__(self):
            self.fills = []

        def ingest(self, fill):
            self.fills.append(fill)
            return None

    sink = Sink()
    result = MT5FillIngestionService(collector, Resolver(), sink).ingest_window("from", "to")

    assert result.applied == 1
    assert len(result.unresolved) == 1
    assert result.unresolved[0].broker_order_id == "204"
    assert [fill.order_id for fill in sink.fills] == ["internal-order-1"]


def test_checkpointed_ingestion_advances_after_clean_batch(monkeypatch):
    monkeypatch.setenv("EXECUTION_ENV", "demo")
    collector = MT5DealCollector(FakeMT5([deal(time_msc=15_000)]))

    class Resolver:
        def resolve(self, broker_order_id, instrument, side):
            return "internal-order-1"

    class Sink:
        def __init__(self):
            self.fills = []

        def ingest(self, fill):
            self.fills.append(fill)
            return None

    class CheckpointStore:
        def __init__(self):
            self.cursor = DealHistoryCursor(watermark_msc=10_000, overlap_msc=5_000)
            self.saved = []

        def load_ingestion_checkpoint(self, **kwargs):
            return self.cursor

        def save_ingestion_checkpoint(self, **kwargs):
            self.saved.append(kwargs)
            self.cursor = kwargs["cursor"]

    checkpoints = CheckpointStore()
    result, next_cursor = MT5FillIngestionService(collector, Resolver(), Sink()).ingest_checkpointed(
        checkpoint_store=checkpoints,
        environment="demo",
        source="mt5",
        stream="deals",
        now_msc=20_000,
    )

    assert result.applied == 1
    assert result.unresolved == ()
    assert next_cursor.watermark_msc == 20_000
    assert checkpoints.saved[-1]["metadata"]["applied"] == 1


def test_checkpointed_ingestion_holds_watermark_at_earliest_unresolved_deal(monkeypatch):
    monkeypatch.setenv("EXECUTION_ENV", "demo")
    collector = MT5DealCollector(FakeMT5([deal(ticket=101, time_msc=12_000)]))

    class Resolver:
        def resolve(self, broker_order_id, instrument, side):
            return None

    class Sink:
        def ingest(self, fill):
            raise AssertionError("unresolved deal must never reach sink")

    class CheckpointStore:
        def __init__(self):
            self.cursor = DealHistoryCursor(watermark_msc=10_000, overlap_msc=5_000)
            self.saved = []

        def load_ingestion_checkpoint(self, **kwargs):
            return self.cursor

        def save_ingestion_checkpoint(self, **kwargs):
            self.saved.append(kwargs)

    checkpoints = CheckpointStore()
    result, next_cursor = MT5FillIngestionService(collector, Resolver(), Sink()).ingest_checkpointed(
        checkpoint_store=checkpoints,
        environment="demo",
        source="mt5",
        stream="deals",
        now_msc=20_000,
    )

    assert result.applied == 0
    assert len(result.unresolved) == 1
    assert next_cursor.watermark_msc == 12_000


def test_supabase_checkpoint_roundtrip_payload(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "server-secret")
    store = SupabaseExecutionStore()
    calls = []

    def fake_request(method, table, **kwargs):
        calls.append((method, table, kwargs))
        if method == "GET":
            return [{"watermark_msc": "12345", "overlap_msc": "5000"}]
        return None

    store._request = fake_request
    cursor = store.load_ingestion_checkpoint(environment="demo", source="mt5", stream="deals")
    assert cursor == DealHistoryCursor(12_345, 5_000)

    store.save_ingestion_checkpoint(
        environment="demo",
        source="mt5",
        stream="deals",
        cursor=DealHistoryCursor(20_000, 5_000),
        metadata={"applied": 3},
    )
    method, table, kwargs = calls[-1]
    assert method == "POST"
    assert table == "execution_ingestion_checkpoints"
    assert kwargs["query"]["on_conflict"] == "environment,source,stream"
    assert kwargs["payload"]["watermark_msc"] == 20_000


def test_cursor_replays_an_overlap_before_advancing(monkeypatch):
    cursor = DealHistoryCursor(watermark_msc=10_000, overlap_msc=5_000)
    start, end = cursor.window(20_000)
    assert start == datetime.fromtimestamp(5, tz=timezone.utc)
    assert end == datetime.fromtimestamp(20, tz=timezone.utc)
    advanced = cursor.advance(20_000)
    assert advanced.watermark_msc == 20_000
    assert advanced.overlap_msc == 5_000


def test_cursor_cannot_move_backwards():
    cursor = DealHistoryCursor(watermark_msc=10_000, overlap_msc=5_000)
    with pytest.raises(ValueError, match="move backwards"):
        cursor.advance(9_999)
    with pytest.raises(ValueError, match="now_msc"):
        cursor.window(9_999)


def test_non_trade_deals_are_excluded(monkeypatch):
    monkeypatch.setenv("EXECUTION_ENV", "demo")
    mt5 = FakeMT5([deal(type=2), deal(ticket=102, order=203, type=1)])
    records = MT5DealCollector(mt5).collect("from", "to")
    assert len(records) == 1
    assert records[0].side == "SELL"


def test_deal_entry_variants_are_preserved(monkeypatch):
    monkeypatch.setenv("EXECUTION_ENV", "demo")
    mt5 = FakeMT5([
        deal(ticket=101, entry=0),
        deal(ticket=102, order=203, entry=1),
        deal(ticket=103, order=204, entry=2),
        deal(ticket=104, order=205, entry=3),
    ])
    records = MT5DealCollector(mt5).collect("from", "to")
    assert [record.metadata["entry"] for record in records] == ["IN", "OUT", "INOUT", "OUT_BY"]


def test_time_msc_is_used_for_execution_timestamp(monkeypatch):
    monkeypatch.setenv("EXECUTION_ENV", "demo")
    mt5 = FakeMT5([deal(time=1, time_msc=2000)])
    record = MT5DealCollector(mt5).collect("from", "to")[0]
    assert record.filled_at == "1970-01-01T00:00:02+00:00"


def test_invalid_trade_identity_is_rejected(monkeypatch):
    monkeypatch.setenv("EXECUTION_ENV", "demo")
    for overrides in ({"ticket": 0}, {"order": 0}, {"symbol": ""}, {"volume": 0}, {"price": 0}):
        with pytest.raises(ValueError):
            MT5DealCollector(FakeMT5([deal(**overrides)])).collect("from", "to")


def test_history_error_is_not_silently_treated_as_empty(monkeypatch):
    monkeypatch.setenv("EXECUTION_ENV", "demo")
    with pytest.raises(RuntimeError, match="history_deals_get failed"):
        MT5DealCollector(FakeMT5(error=(1, "history failure"))).collect("from", "to")


def test_live_environment_is_rejected(monkeypatch):
    monkeypatch.setenv("EXECUTION_ENV", "live")
    with pytest.raises(RuntimeError, match="demo-only"):
        MT5DealCollector(FakeMT5([]))
