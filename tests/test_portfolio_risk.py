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


def test_missing_correlation_is_rejected_by_default():
    result = PortfolioRiskEngine().evaluate(
        exposures=(
            Exposure("EURUSD", Decimal("1000"), Decimal("0.10"), Decimal("0.2")),
            Exposure("GBPUSD", Decimal("1000"), Decimal("0.10"), Decimal("0.2")),
        ),
        account_equity=Decimal("10000"),
        margin_fraction=Decimal("0.01"),
        correlation={},
    )
    assert not result.approved
    assert "PORTFOLIO_CORRELATION_INPUT_MISSING" in result.reasons


def test_beta_limit_is_enforced():
    engine = PortfolioRiskEngine(
        PortfolioRiskLimits(
            max_abs_beta_exposure=Decimal("0.05"),
            require_complete_correlation=False,
        )
    )
    result = engine.evaluate(
        exposures=(Exposure("EURUSD", Decimal("5000"), Decimal("0.10"), Decimal("0.2")),),
        account_equity=Decimal("10000"),
        margin_fraction=Decimal("0.01"),
        correlation={},
    )
    assert not result.approved
    assert "PORTFOLIO_BETA_LIMIT" in result.reasons


def test_invalid_risk_limit_is_rejected():
    import pytest
    with pytest.raises(ValueError):
        PortfolioRiskLimits(max_abs_beta_exposure=Decimal("2"))
