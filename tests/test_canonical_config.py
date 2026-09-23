from decimal import Decimal

import pytest

from apps.trading_runtime.canonical import CanonicalConfig


def valid_config(**overrides):
    data = dict(
        node_id="ci",
        symbols=("EURUSD",),
        environment="demo",
        timeframe="H1",
        bars_per_symbol=100,
        max_order_risk=Decimal("0.005"),
        max_per_strategy_risk=Decimal("0.01"),
        max_per_instrument_risk=Decimal("0.01"),
        max_total_risk=Decimal("0.03"),
    )
    data.update(overrides)
    return CanonicalConfig(**data)


def test_risk_limits_are_single_source_of_truth():
    config = valid_config(
        risk_max_drawdown=Decimal("0.07"),
        risk_max_daily_loss=Decimal("0.02"),
        risk_max_open_positions=4,
        risk_min_broker_health=Decimal("0.85"),
        risk_min_data_health=Decimal("0.90"),
    )
    config.validate()
    assert config.risk_max_daily_loss == Decimal("0.02")


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_order_risk": Decimal("0.02"), "max_per_strategy_risk": Decimal("0.01")},
        {"max_per_strategy_risk": Decimal("0.04"), "max_total_risk": Decimal("0.03")},
        {"max_per_instrument_risk": Decimal("0.04"), "max_total_risk": Decimal("0.03")},
        {"portfolio_max_net_notional_fraction": Decimal("0.80"), "portfolio_max_gross_notional_fraction": Decimal("0.75")},
        {"risk_max_open_positions": 0},
    ],
)
def test_inconsistent_or_invalid_limits_are_rejected(overrides):
    with pytest.raises(ValueError):
        valid_config(**overrides).validate()


def test_live_environment_is_unconditionally_rejected():
    with pytest.raises(ValueError, match="demo environment"):
        valid_config(environment="live").validate()
