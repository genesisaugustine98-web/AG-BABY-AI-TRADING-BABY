from decimal import Decimal

import pytest

from packages.fill_accounting import BrokerConfirmedFill, FillAccountingEngine, PositionState, apply_fill


def fill(
    fill_id: str,
    side: str,
    quantity: str,
    price: str,
    filled_at: str,
    *,
    order_id: str = "order-1",
    broker_fill_id: str | None = None,
    financing: str = "0",
):
    return BrokerConfirmedFill(
        fill_id=fill_id,
        order_id=order_id,
        instrument="EURUSD",
        side=side,
        quantity=Decimal(quantity),
        price=Decimal(price),
        filled_at=filled_at,
        broker_fill_id=broker_fill_id,
        financing=Decimal(financing),
    )


def test_buy_then_sell_realizes_quote_currency_pnl():
    state = PositionState("EURUSD")
    state = apply_fill(state, fill("f1", "BUY", "100", "1.1000", "2026-09-17T07:00:00Z"))
    state = apply_fill(state, fill("f2", "SELL", "40", "1.1030", "2026-09-17T07:01:00Z"))

    assert state.net_quantity == Decimal("60")
    assert state.average_price == Decimal("1.1000")
    assert state.realized_pnl == Decimal("0.1200")


def test_short_then_cover_realizes_profit():
    engine = FillAccountingEngine()
    engine.ingest(fill("f1", "SELL", "100", "1.1000", "2026-09-17T07:00:00Z"))
    result = engine.ingest(fill("f2", "BUY", "60", "1.0970", "2026-09-17T07:01:00Z"))

    assert result.position.net_quantity == Decimal("-40")
    assert result.position.average_price == Decimal("1.1000")
    assert result.position.realized_pnl == Decimal("0.1800")


def test_reversal_closes_old_side_and_opens_remainder_at_new_price():
    engine = FillAccountingEngine()
    engine.ingest(fill("f1", "BUY", "100", "1.1000", "2026-09-17T07:00:00Z"))
    result = engine.ingest(fill("f2", "SELL", "150", "1.1020", "2026-09-17T07:01:00Z"))

    assert result.position.net_quantity == Decimal("-50")
    assert result.position.average_price == Decimal("1.1020")
    assert result.position.realized_pnl == Decimal("0.2000")


def test_duplicate_fill_is_idempotent():
    engine = FillAccountingEngine()
    first = engine.ingest(fill("f1", "BUY", "100", "1.1000", "2026-09-17T07:00:00Z"))
    second = engine.ingest(fill("f1", "BUY", "100", "1.1000", "2026-09-17T07:00:00Z"))

    assert first.status == "APPLIED"
    assert second.status == "DUPLICATE"
    assert len(engine.fills) == 1
    assert second.position.net_quantity == Decimal("100")


def test_same_fill_id_with_different_payload_is_a_conflict():
    engine = FillAccountingEngine()
    engine.ingest(fill("f1", "BUY", "100", "1.1000", "2026-09-17T07:00:00Z"))

    with pytest.raises(ValueError, match="fill_id_conflict:f1"):
        engine.ingest(fill("f1", "BUY", "100", "1.1010", "2026-09-17T07:00:00Z"))


def test_out_of_order_arrival_is_replayed_by_execution_time():
    engine = FillAccountingEngine()
    engine.ingest(fill("f2", "SELL", "40", "1.1030", "2026-09-17T07:01:00Z"))
    result = engine.ingest(fill("f1", "BUY", "100", "1.1000", "2026-09-17T07:00:00Z"))

    assert result.position.net_quantity == Decimal("60")
    assert result.position.realized_pnl == Decimal("0.1200")


def test_financing_is_tracked_separately_from_price_pnl():
    engine = FillAccountingEngine()
    engine.ingest(fill("f1", "BUY", "100", "1.1000", "2026-09-17T07:00:00Z", financing="-0.25"))
    result = engine.ingest(fill("f2", "SELL", "100", "1.1000", "2026-09-17T07:01:00Z", financing="0.10"))

    assert result.position.net_quantity == Decimal("0")
    assert result.position.realized_pnl == Decimal("0")
    assert result.position.financing_pnl == Decimal("-0.15")


def test_invalid_quantity_and_price_are_rejected():
    with pytest.raises(ValueError):
        fill("bad-q", "BUY", "0", "1.1000", "2026-09-17T07:00:00Z")
    with pytest.raises(ValueError):
        fill("bad-p", "BUY", "10", "0", "2026-09-17T07:00:00Z")
