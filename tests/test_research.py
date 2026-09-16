from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest

from apps.research.backtest import BacktestConfig, run_replay
from apps.research.cost_model import ExecutionCosts
from apps.research.data_contract import MarketObservation


def bar(i: int, close: str, *, usable_lag_seconds: int = 0) -> MarketObservation:
    t = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i)
    return MarketObservation(
        instrument="EURUSD",
        event_time=t,
        usable_at=t + timedelta(seconds=usable_lag_seconds),
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        source="test",
        source_version="v1",
        observation_id=f"bar-{i}",
    )


def test_future_information_is_not_tradable():
    bars = [
        bar(0, "1.1000", usable_lag_seconds=5),
        bar(1, "1.1010", usable_lag_seconds=5),
        bar(2, "1.1020", usable_lag_seconds=5),
    ]
    trades = run_replay(bars, lambda _: 1, BacktestConfig(horizon_bars=1))
    assert trades == []


def test_later_available_information_can_be_used():
    bars = [
        bar(0, "1.1000", usable_lag_seconds=5),
        bar(1, "1.1010"),
        bar(2, "1.1020"),
    ]
    trades = run_replay(bars, lambda _: 1, BacktestConfig(horizon_bars=1))
    assert len(trades) == 1
    assert trades[0].observation_id == "bar-1"


def test_delayed_entry_is_explicit():
    bars = [bar(0, "1.1000"), bar(1, "1.1010"), bar(2, "1.1020"), bar(3, "1.1030")]
    trades = run_replay(bars, lambda _: 1, BacktestConfig(horizon_bars=1, delay_bars=1))
    assert trades[0].entry_close == Decimal("1.1010")
    assert trades[0].exit_close == Decimal("1.1020")


def test_costs_reduce_return():
    bars = [bar(0, "1.1000"), bar(1, "1.1010")]
    trades = run_replay(
        bars,
        lambda _: 1,
        BacktestConfig(horizon_bars=1, costs=ExecutionCosts(Decimal("0.0010"), Decimal("0.0002"), Decimal("0.0001"))),
    )
    assert trades[0].gross_return > trades[0].net_return
    assert trades[0].net_return == trades[0].gross_return - Decimal("0.0013")


def test_invalid_price_rejected():
    with pytest.raises(ValueError):
        bar(0, "0")
