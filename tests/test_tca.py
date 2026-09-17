from decimal import Decimal

from packages.fill_accounting import BrokerConfirmedFill
from packages.tca import MarkoutObservation, ReferenceQuote, analyze_tca


def mk(fill_id, side, quantity, price, at):
    return BrokerConfirmedFill(
        fill_id=fill_id,
        order_id="order-1",
        instrument="EURUSD",
        side=side,
        quantity=Decimal(quantity),
        price=Decimal(price),
        filled_at=at,
    )


def test_buy_tca_computes_vwap_adverse_slippage_and_favorable_markout():
    result = analyze_tca(
        fills=(
            mk("f1", "BUY", "60", "1.1002", "2026-09-17T07:00:00Z"),
            mk("f2", "BUY", "40", "1.1004", "2026-09-17T07:00:01Z"),
        ),
        requested_quantity=Decimal("100"),
        arrival_quote=ReferenceQuote(Decimal("1.1000"), Decimal("1.1002"), "2026-09-17T06:59:59Z"),
        markouts=(MarkoutObservation("1m", Decimal("1.1014"), "2026-09-17T07:01:00Z"),),
    )

    assert result.status == "OK"
    assert result.execution_vwap == Decimal("1.10028")
    assert result.arrival_mid == Decimal("1.1001")
    assert result.arrival_spread == Decimal("0.0002")
    assert result.signed_slippage_price == Decimal("0.00018")
    assert result.markouts_bps[0][0] == "1m"
    assert result.markouts_bps[0][1] > 0


def test_sell_tca_marks_a_lower_future_mid_as_favorable():
    result = analyze_tca(
        fills=(mk("f1", "SELL", "100", "1.1000", "2026-09-17T07:00:00Z"),),
        requested_quantity=Decimal("100"),
        arrival_quote=ReferenceQuote(Decimal("1.0998"), Decimal("1.1000"), "2026-09-17T06:59:59Z"),
        markouts=(MarkoutObservation("5m", Decimal("1.0980"), "2026-09-17T07:05:00Z"),),
    )
    assert result.markouts_bps[0][1] > 0


def test_missing_arrival_quote_is_explicitly_unknown():
    result = analyze_tca(
        fills=(mk("f1", "BUY", "10", "1.1000", "2026-09-17T07:00:00Z"),),
        requested_quantity=Decimal("10"),
        arrival_quote=None,
    )
    assert result.status == "UNKNOWN_ARRIVAL_QUOTE"
    assert result.execution_vwap == Decimal("1.1000")
    assert result.signed_slippage_bps is None
