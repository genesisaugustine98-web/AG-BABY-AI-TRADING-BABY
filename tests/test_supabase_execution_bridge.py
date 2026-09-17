from decimal import Decimal

import pytest

from integrations.supabase_execution import DurableFillAccountingBridge
from packages.fill_accounting import BrokerConfirmedFill, PositionState


class FakeStore:
    def __init__(self):
        self.fills = {}
        self.positions = []

    def insert_fill(self, fill):
        existing = self.fills.get(fill.fill_id)
        if existing is not None:
            if existing.fingerprint != fill.fingerprint:
                raise RuntimeError(f"fill_id_conflict:{fill.fill_id}")
            return fill.fill_id, False
        self.fills[fill.fill_id] = fill
        return fill.fill_id, True

    def load_fills(self, instrument):
        return tuple(sorted((f for f in self.fills.values() if f.instrument == instrument), key=lambda f: (f.filled_at, f.fill_id)))

    def upsert_position(self, *, environment, state):
        self.positions.append((environment, state))


def mk(fill_id, side, quantity, price, filled_at):
    return BrokerConfirmedFill(
        fill_id=fill_id,
        order_id="order-1",
        instrument="USDJPY",
        side=side,
        quantity=Decimal(quantity),
        price=Decimal(price),
        filled_at=filled_at,
    )


def test_bridge_projects_only_confirmed_persisted_fills():
    store = FakeStore()
    bridge = DurableFillAccountingBridge(store, environment="demo")

    state = bridge.ingest(mk("f1", "BUY", "2", "150.00", "2026-09-17T07:00:00Z"))
    assert state == PositionState("USDJPY", Decimal("2"), Decimal("150.00"))
    assert store.positions[-1][0] == "demo"


def test_bridge_replays_all_persisted_fills_after_duplicate_delivery():
    store = FakeStore()
    bridge = DurableFillAccountingBridge(store, environment="demo")
    bridge.ingest(mk("f1", "BUY", "2", "150.00", "2026-09-17T07:00:00Z"))
    state = bridge.ingest(mk("f1", "BUY", "2", "150.00", "2026-09-17T07:00:00Z"))
    assert state.net_quantity == Decimal("2")
    assert len(store.fills) == 1


def test_bridge_rejects_conflicting_duplicate_identity():
    store = FakeStore()
    bridge = DurableFillAccountingBridge(store, environment="demo")
    bridge.ingest(mk("f1", "BUY", "2", "150.00", "2026-09-17T07:00:00Z"))
    with pytest.raises(RuntimeError, match="fill_id_conflict:f1"):
        bridge.ingest(mk("f1", "BUY", "2", "150.10", "2026-09-17T07:00:00Z"))


def test_bridge_can_flatten_and_persist_flat_state():
    store = FakeStore()
    bridge = DurableFillAccountingBridge(store, environment="demo")
    bridge.ingest(mk("f1", "BUY", "2", "150.00", "2026-09-17T07:00:00Z"))
    state = bridge.ingest(mk("f2", "SELL", "2", "150.20", "2026-09-17T07:01:00Z"))
    assert state.net_quantity == Decimal("0")
    assert state.average_price is None
    assert state.realized_pnl == Decimal("0.40")
