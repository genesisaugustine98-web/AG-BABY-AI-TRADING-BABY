from datetime import datetime, timezone
from decimal import Decimal

from apps.research.h10_ingest import H10Observation
from apps.research.reference_backtest import run_reference_backtest
from apps.research.reference_metrics import summarize_detailed


def obs(day: int, value: str) -> H10Observation:
    t = datetime(2026, 1, day, tzinfo=timezone.utc)
    return H10Observation(
        instrument="EURUSD_REFERENCE",
        event_time=t,
        usable_at=t,
        value=Decimal(value),
        source="test",
        source_version="v1",
        observation_id=f"o{day}",
    )


def test_metrics_capture_drawdown_and_profit_factor():
    bars = [obs(1, "1.0000"), obs(2, "1.0100"), obs(3, "1.0200"), obs(4, "1.0100")]
    trades = run_reference_backtest(bars, instrument="EURUSD_REFERENCE", rule="momentum")
    metrics = summarize_detailed(trades)
    assert metrics["n"] == 2
    assert metrics["win_rate_net"] == Decimal("0.5")
    assert metrics["profit_factor"] is not None
    assert metrics["max_drawdown"] is not None
    assert metrics["gross_exposure"] == Decimal("2")


def test_empty_sample_is_explicit():
    metrics = summarize_detailed([])
    assert metrics["n"] == 0
    assert metrics["max_drawdown"] is None
    assert metrics["profit_factor"] is None
