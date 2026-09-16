from datetime import datetime, timezone
from decimal import Decimal

import pytest

from packages.accounting import (
    BrokerConfirmedFill,
    ConfirmedFillProcessor,
    PositionBook,
    execution_tca,
)
from packages.execution_ledger import AppendOnlyLedger


def fill(fill_id, side, qty, price, *, confirmed=True):
    return BrokerConfirmedFill(
        fill_id=fill_id,
        broker_order_id="broker-1",
        client_order_id="client-1",
        instrument="USDJPY",
        side=side,
        quantity=Decimal(qty),
        price=Decimal(price),
        occurred_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
        broker="demo",
        confirmed=confirmed,
    )


def test_unconfirmed_fill_cannot_enter_accounting():
    with pytest.raises(ValueError, match="unconfirmed"):
        PositionBook().apply(fill("f1", "BUY", "1", "150", confirmed=False))


def test_duplicate_fill_is_idempotent():
    ledger = AppendOnlyLedger()
    processor = ConfirmedFillProcessor(ledger)
    first = processor.process(fill("f1", "BUY", "1", "150"))
    second = processor.process(fill("f1", "BUY", "1", "150"))
    assert first.duplicate is False
    assert second.duplicate is True
    assert len(ledger.events) == 1
    assert second.position.net_quantity == Decimal("1")


def test_partial_fills_build_weighted_average():
    processor = ConfirmedFillProcessor(AppendOnlyLedger())
    processor.process(fill("f1", "BUY", "1", "150"))
    result = processor.process(fill("f2", "BUY", "2", "153"))
    assert result.position.net_quantity == Decimal("3")
    assert result.position.average_price == Decimal("152")
    assert result.position.realized_pnl == Decimal("0")


def test_long_close_realizes_profit_and_flattening_resets_average():
    processor = ConfirmedFillProcessor(AppendOnlyLedger())
    processor.process(fill("f1", "BUY", "2", "150"))
    result = processor.process(fill("f2", "SELL", "2", "155"))
    assert result.position.net_quantity == Decimal("0")
    assert result.position.average_price == Decimal("0")
    assert result.position.realized_pnl == Decimal("10")


def test_short_close_realizes_profit():
    processor = ConfirmedFillProcessor(AppendOnlyLedger())
    processor.process(fill("f1", "SELL", "2", "150"))
    result = processor.process(fill("f2", "BUY", "2", "145"))
    assert result.position.net_quantity == Decimal("0")
    assert result.position.realized_pnl == Decimal("10")


def test_partial_close_keeps_remaining_entry_price():
    processor = ConfirmedFillProcessor(AppendOnlyLedger())
    processor.process(fill("f1", "BUY", "3", "150"))
    result = processor.process(fill("f2", "SELL", "1", "155"))
    assert result.position.net_quantity == Decimal("2")
    assert result.position.average_price == Decimal("150")
    assert result.position.realized_pnl == Decimal("5")


def test_reverse_position_uses_remainder_at_new_fill_price():
    processor = ConfirmedFillProcessor(AppendOnlyLedger())
    processor.process(fill("f1", "BUY", "1", "150"))
    result = processor.process(fill("f2", "SELL", "3", "155"))
    assert result.position.net_quantity == Decimal("-2")
    assert result.position.average_price == Decimal("155")
    assert result.position.realized_pnl == Decimal("5")


def test_invalid_quantity_and_price_rejected():
    with pytest.raises(ValueError, match="quantity"):
        fill("f1", "BUY", "0", "150").validate()
    with pytest.raises(ValueError, match="price"):
        fill("f1", "BUY", "1", "0").validate()


def test_tca_keeps_unavailable_reference_as_unknown():
    metrics = execution_tca(None, [fill("f1", "BUY", "1", "150"), fill("f2", "BUY", "1", "152")])
    assert metrics["filled_quantity"] == Decimal("2")
    assert metrics["execution_vwap"] == Decimal("151")
    assert metrics["slippage_price"] is None


def test_tca_buy_slippage_is_signed_worse_as_positive():
    metrics = execution_tca(Decimal("149"), [fill("f1", "BUY", "1", "150")])
    assert metrics["slippage_price"] == Decimal("1")


def test_tca_sell_slippage_is_signed_worse_as_positive():
    metrics = execution_tca(Decimal("151"), [fill("f1", "SELL", "1", "150")])
    assert metrics["slippage_price"] == Decimal("1")
