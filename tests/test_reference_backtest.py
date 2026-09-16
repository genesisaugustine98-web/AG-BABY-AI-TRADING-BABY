from datetime import datetime, timezone
from decimal import Decimal

from apps.research.h10_ingest import H10Observation
from apps.research.reference_backtest import run_reference_backtest, summarize_reference_trades


def obs(day: int, value: str, *, usable_lag_days: int = 0) -> H10Observation:
    event = datetime(2026, 1, day, tzinfo=timezone.utc)
    usable = datetime(2026, 1, day + usable_lag_days, tzinfo=timezone.utc)
    return H10Observation(
        instrument="EURUSD_REFERENCE",
        event_time=event,
        usable_at=usable,
        value=Decimal(value),
        source="test",
        source_version="v1",
        observation_id=f"o{day}",
    )


def test_momentum_and_reversal_are_opposites():
    bars = [obs(1, "1.0000"), obs(2, "1.0100"), obs(3, "1.0000"), obs(4, "1.0200")]
    momentum = run_reference_backtest(bars, instrument="EURUSD_REFERENCE", rule="momentum")
    reversal = run_reference_backtest(bars, instrument="EURUSD_REFERENCE", rule="reversal")
    assert momentum[0].signal == 1
    assert reversal[0].signal == -1
    assert momentum[0].gross_return == Decimal("1.00") / Decimal("1.01") - Decimal("1")
    assert reversal[0].gross_return == Decimal("1") - Decimal("1.00") / Decimal("1.01")


def test_unavailable_current_observation_is_skipped():
    bars = [obs(1, "1.0000", usable_lag_days=2), obs(2, "1.0100"), obs(3, "1.0200")]
    trades = run_reference_backtest(bars, instrument="EURUSD_REFERENCE", rule="momentum")
    assert len(trades) == 0


def test_costs_reduce_net_return():
    bars = [obs(1, "1.0000"), obs(2, "1.0100"), obs(3, "1.0200")]
    trades = run_reference_backtest(
        bars,
        instrument="EURUSD_REFERENCE",
        rule="momentum",
        one_way_cost_bps=Decimal("5"),
    )
    assert trades[0].net_return == trades[0].gross_return - Decimal("0.001")


def test_summary_handles_empty_and_nonempty():
    assert summarize_reference_trades([])["n"] == 0
    bars = [obs(1, "1.0000"), obs(2, "1.0100"), obs(3, "1.0200")]
    trades = run_reference_backtest(bars, instrument="EURUSD_REFERENCE", rule="momentum")
    summary = summarize_reference_trades(trades)
    assert summary["n"] == 1
    assert summary["win_rate_net"] == Decimal("1")
