from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest

from apps.research.experiment_suite import chronological_splits, run_fixed_grid
from apps.research.h10_ingest import H10Observation


def obs(day: int, value: str) -> H10Observation:
    t = datetime(2026, 1, day, tzinfo=timezone.utc)
    return H10Observation(
        instrument="EURUSD_REFERENCE",
        event_time=t,
        usable_at=t,
        value=Decimal(value),
        source="test",
        source_version="v1",
        observation_id=f"x-{day}",
    )


def test_splits_are_strictly_chronological():
    rows = [obs(d, f"1.{1000+d}") for d in range(1, 13)]
    splits = chronological_splits(rows)
    assert splits[0].end < splits[1].start < splits[1].end < splits[2].start


def test_fixed_grid_covers_splits_rules_and_costs():
    rows = [obs(d, f"1.{1000+d}") for d in range(1, 16)]
    result = run_fixed_grid(rows, instrument="EURUSD_REFERENCE", costs_bps=(Decimal("0"), Decimal("2")))
    assert len(result) == 3 * 2 * 2
    assert {x["split"] for x in result} == {"development", "validation", "holdout"}
    assert {x["rule"] for x in result} == {"momentum", "reversal"}
    assert {x["one_way_cost_bps"] for x in result} == {"0", "2"}


def test_requires_three_dates():
    with pytest.raises(ValueError):
        chronological_splits([obs(1, "1.1"), obs(2, "1.2")])
