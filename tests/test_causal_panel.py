from datetime import datetime, timezone
from decimal import Decimal

import pytest

from apps.research.causal_panel import (
    assert_no_future_information,
    build_release_states,
    latest_causal_state,
)
from apps.research.h10_ingest import H10Observation


def obs(day: int, value: str, usable_at: str) -> H10Observation:
    return H10Observation(
        instrument="EURUSD_REFERENCE",
        event_time=datetime(2026, 9, day, tzinfo=timezone.utc),
        usable_at=datetime.fromisoformat(usable_at),
        value=Decimal(value),
        source="Federal Reserve Board H.10",
        source_version="H10-release-test",
        observation_id=f"test-{day}",
    )


def test_release_uses_latest_observation_available_at_release():
    observations = [
        obs(10, "1.10", "2026-09-14T16:15:00+00:00"),
        obs(11, "1.11", "2026-09-14T16:15:00+00:00"),
    ]
    state = latest_causal_state(
        observations,
        instrument="EURUSD_REFERENCE",
        release_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
    )
    assert state.latest_value == Decimal("1.11")
    assert state.prior_value == Decimal("1.10")
    assert state.prior_return == pytest.approx(Decimal("0.0090909090909090909"))


def test_future_observation_is_excluded():
    observations = [
        obs(10, "1.10", "2026-09-14T16:15:00+00:00"),
        obs(11, "1.11", "2026-09-16T16:15:00+00:00"),
    ]
    state = latest_causal_state(
        observations,
        instrument="EURUSD_REFERENCE",
        release_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
    )
    assert state.latest_value == Decimal("1.10")
    assert state.prior_value is None
    assert_no_future_information([state])


def test_release_times_must_be_timezone_aware():
    observations = [obs(10, "1.10", "2026-09-14T16:15:00+00:00")]
    with pytest.raises(ValueError, match="timezone-aware"):
        build_release_states(
            observations,
            release_times=[datetime(2026, 9, 15)],
            instruments=["EURUSD_REFERENCE"],
        )
