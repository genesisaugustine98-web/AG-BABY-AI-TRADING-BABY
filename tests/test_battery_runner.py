from datetime import datetime, timedelta, timezone
from decimal import Decimal

from apps.research.battery_runner import run_battery
from apps.research.h10_ingest import H10Observation


def obs(i: int, usable_offset_days: int = 0) -> H10Observation:
    event = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=i)
    usable = event + timedelta(days=usable_offset_days)
    return H10Observation(
        instrument="EURUSD_REFERENCE",
        event_time=event,
        usable_at=usable,
        value=Decimal("1.10") + Decimal(i) / Decimal("1000"),
        source="test",
        source_version="test-v1",
        observation_id=f"T:{i}",
    )


def config() -> dict[str, object]:
    return {
        "hypotheses": [
            {
                "hypothesis_id": "H1",
                "statement": "test",
                "rule": "momentum",
                "instruments": ["EURUSD_REFERENCE"],
                "horizons": [1],
                "development_fraction": "0.60",
                "validation_fraction": "0.20",
                "holdout_fraction": "0.20",
            }
        ],
        "one_way_cost_bps_grid": [0],
        "required_splits": ["development", "validation", "holdout"],
    }


def test_revised_historical_observations_are_blocked_when_not_available_at_event_time():
    results = run_battery([obs(i, usable_offset_days=7) for i in range(20)], config=config())
    assert results
    assert all(row.status == "blocked" for row in results)
    assert all("unavailable" in row.reason for row in results)


def test_causally_available_series_can_execute():
    results = run_battery([obs(i, usable_offset_days=0) for i in range(20)], config=config())
    completed = [row for row in results if row.status == "completed"]
    assert len(completed) == 3
    assert all(row.summary is not None for row in completed)
