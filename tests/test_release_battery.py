from datetime import datetime, timedelta, timezone
from decimal import Decimal

from apps.research.h10_ingest import H10Observation
from apps.research.release_battery import run_release_backtest, summarize_release_trades


def _obs(day: int, value: str, usable_day: int) -> H10Observation:
    return H10Observation(
        instrument="EURUSD_REFERENCE",
        event_time=datetime(2026, 1, day, tzinfo=timezone.utc),
        usable_at=datetime(2026, 1, usable_day, 16, tzinfo=timezone.utc),
        value=Decimal(value),
        source="test",
        source_version="test",
        observation_id=f"o-{day}",
    )


def test_future_observation_is_not_used_in_release_state():
    observations = [
        _obs(1, "1.10", 2),
        _obs(2, "1.11", 3),
        _obs(3, "1.09", 4),
    ]
    releases = [datetime(2026, 1, d, tzinfo=timezone.utc) for d in (1, 2, 3, 4)]
    trades = run_release_backtest(
        observations,
        instrument="EURUSD_REFERENCE",
        release_times=releases,
        rule="momentum",
        horizon_releases=1,
    )
    assert trades == []


def test_release_backtest_uses_only_released_information_and_costs():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    observations = [
        H10Observation("EURUSD_REFERENCE", base, base, Decimal("1.00"), "test", "v1", "o1"),
        H10Observation("EURUSD_REFERENCE", base + timedelta(days=1), base + timedelta(days=1), Decimal("1.01"), "test", "v1", "o2"),
        H10Observation("EURUSD_REFERENCE", base + timedelta(days=2), base + timedelta(days=2), Decimal("1.02"), "test", "v1", "o3"),
        H10Observation("EURUSD_REFERENCE", base + timedelta(days=3), base + timedelta(days=3), Decimal("1.03"), "test", "v1", "o4"),
    ]
    releases = [base + timedelta(days=d) for d in range(4)]
    trades = run_release_backtest(
        observations,
        instrument="EURUSD_REFERENCE",
        release_times=releases,
        rule="momentum",
        horizon_releases=1,
        one_way_cost_bps=Decimal("5"),
    )
    assert len(trades) == 2
    assert trades[0].signal == 1
    assert trades[0].net_return == (Decimal("1.02") / Decimal("1.01") - Decimal("1")) - Decimal("0.001")
    assert summarize_release_trades(trades)["n"] == 2
