from decimal import Decimal

from packages.portfolio_risk import Exposure, PortfolioRiskEngine


def test_portfolio_risk_accounts_for_correlation_and_limits():
    engine = PortfolioRiskEngine()
    result = engine.evaluate(
        exposures=(
            Exposure("EURUSD", Decimal("4000"), Decimal("0.10"), Decimal("0.2")),
            Exposure("GBPUSD", Decimal("-2000"), Decimal("0.12"), Decimal("0.1")),
        ),
        account_equity=Decimal("10000"),
        margin_fraction=Decimal("0.10"),
        correlation={("EURUSD", "GBPUSD"): Decimal("0.80")},
    )
    assert result.gross_fraction == Decimal("0.6")
    assert result.net_fraction == Decimal("0.2")
    assert result.approved
    assert result.beta_exposure == Decimal("0.06")


def test_portfolio_risk_rejects_margin():
    result = PortfolioRiskEngine().evaluate(
        exposures=(),
        account_equity=Decimal("10000"),
        margin_fraction=Decimal("0.70"),
        correlation={},
    )
    assert not result.approved
    assert "PORTFOLIO_MARGIN_LIMIT" in result.reasons
