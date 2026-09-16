"""Convert current H.10 historical values into PIT-scheduled observations.

The resulting dataset is schedule-correct for information availability, but its
values are the Federal Reserve's current historical values and may include later
revisions. It must not be described as a true real-time vintage database.
"""
from __future__ import annotations

from datetime import date
from .h10_ingest import H10Observation, parse_h10_daily_csv, h10_release_timestamp
from .h10_vintage import h10_release_date_for_observation


def parse_current_history_with_schedule(payload: str) -> list[H10Observation]:
    """Parse current H.10 history and assign scheduled publication availability per observation."""
    base = parse_h10_daily_csv(payload, usable_at=h10_release_timestamp(date(1970, 1, 1)))
    out: list[H10Observation] = []
    for item in base:
        release_date = h10_release_date_for_observation(item.event_time.date())
        release_at = h10_release_timestamp(release_date)
        out.append(
            H10Observation(
                instrument=item.instrument,
                event_time=item.event_time,
                usable_at=release_at,
                value=item.value,
                source=item.source,
                source_version=f"current-history-retrieved-snapshot;scheduled-release-{release_date.isoformat()}",
                observation_id=item.observation_id,
                execution_grade=False,
            )
        )
    return out
