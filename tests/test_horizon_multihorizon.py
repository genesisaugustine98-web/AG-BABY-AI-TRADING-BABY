from decimal import Decimal

import pytest

from packages.horizon import (
    Timeframe,
    bars_to_seconds,
    default_horizon_plan,
    native_horizon_ok,
    timeframe_seconds,
)
from packages.multihorizon import Signal, compose_signals


def test_timeframe_conversion_and_plan():
    assert timeframe_seconds(Timeframe.H1) == 3600
    assert bars_to_seconds("M15", 4) == 3600
    assert any(spec.name == "tactical" and spec.timeframe == Timeframe.H1 for spec in default_horizon_plan())


def test_native_horizon_rejects_slower_execution_than_signal():
    assert native_horizon_ok(signal_horizon_seconds=900, execution_seconds=60)
    assert not native_horizon_ok(signal_horizon_seconds=60, execution_seconds=60)


def test_multihorizon_does_not_double_count_same_mechanism():
    signals = (
        Signal("rsi", "technical", Decimal("0.9"), Decimal("0.9"), 900),
        Signal("macd", "technical", Decimal("0.8"), Decimal("0.8"), 3600),
        Signal("macro", "macro", Decimal("0.5"), Decimal("0.7"), 86400),
    )
    composite = compose_signals(signals)
    assert composite.effective_components == 2
    assert -1 <= composite.score <= 1
    assert 0 <= composite.confidence <= 1


def test_signal_bounds():
    with pytest.raises(ValueError):
        Signal("x", "m", Decimal("1.1"), Decimal("0.5"), 60)
