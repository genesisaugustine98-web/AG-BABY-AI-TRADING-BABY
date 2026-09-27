from decimal import Decimal

from packages.portfolio_engine import PortfolioEngine, PositionSnapshot


def test_portfolio_engine_is_fail_closed_until_authoritative_snapshot():
    book = PortfolioEngine()
    try:
        book.as_portfolio_state()
    except RuntimeError:
        pass
    else:
        raise AssertionError("portfolio must not expose readiness without broker truth")


def test_portfolio_engine_aggregates_account_positions_and_risk():
    book = PortfolioEngine()
    book.update_account(captured_at_ms=1_000, balance=Decimal("10000"), equity=Decimal("10200"))
    book.update_positions(
        (
            PositionSnapshot("EURUSD", Decimal("1")),
            PositionSnapshot("GBPUSD", Decimal("0")),
            PositionSnapshot("USDJPY", Decimal("-2")),
        ),
        captured_at_ms=1_001,
    )
    book.reserve_order_risk("a", Decimal("0.005"))
    book.reserve_order_risk("b", Decimal("0.002"))
    state = book.as_portfolio_state()
    assert state.equity == Decimal("10200")
    assert state.open_positions == 2
    assert state.gross_risk_fraction == Decimal("0.007")
    assert state.account_drawdown_fraction == Decimal("0")


def test_portfolio_drawdown_uses_peak_equity():
    book = PortfolioEngine()
    book.update_account(captured_at_ms=1_000, balance=Decimal("10000"), equity=Decimal("10000"))
    book.update_account(captured_at_ms=2_000, balance=Decimal("9800"), equity=Decimal("9800"))
    state = book.as_portfolio_state()
    assert state.account_drawdown_fraction == Decimal("0.02")
