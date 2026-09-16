from datetime import datetime, timezone
from decimal import Decimal

from apps.research.experiment_runner import ResearchSplit, run_fixed_grid
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
        observation_id=f"o{day}",
    )


def test_fixed_grid_emits_all_declared_combinations():
    rows = run_fixed_grid(
        [obs(1, "1.00"), obs(2, "1.01"), obs(3, "1.02"), obs(4, "1.01"), obs(5, "1.03")],
        instruments=["EURUSD_REFERENCE"],
        split=ResearchSplit(development_end=datetime(2026, 1, 2, tzinfo=timezone.utc).date(), validation_end=datetime(2026, 1, 3, tzinfo=timezone.utc).date()),
        horizons=(1,),
        costs_bps=(Decimal("0"), Decimal("5")),
    )
    assert len(rows) == 3 * 2 * 1 * 2
    assert {row["sample"] for row in rows} == {"development", "validation", "holdout"}


def test_split_is_chronological_and_non_overlapping():
    split = ResearchSplit(development_end=datetime(2026, 1, 2, tzinfo=timezone.utc).date(), validation_end=datetime(2026, 1, 3, tzinfo=timezone.utc).date())
    assert split.label(datetime(2026, 1, 2, tzinfo=timezone.utc).date()) == "development"
    assert split.label(datetime(2026, 1, 3, tzinfo=timezone.utc).date()) == "validation"
    assert split.label(datetime(2026, 1, 4, tzinfo=timezone.utc).date()) == "holdout"
