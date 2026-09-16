"""Build causal information sets from release-vintage-tagged H.10 observations.

A release event is the decision clock.  An observation is eligible only when its
``usable_at`` timestamp is at or before the release timestamp.  This module does
not claim to reconstruct the original Fed revision history; when source files are
revised, that limitation remains explicit in the resulting metadata.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Iterable

from .h10_ingest import H10Observation


@dataclass(frozen=True)
class ReleaseState:
    release_at: datetime
    instrument: str
    latest_observation_time: datetime | None
    latest_value: Decimal | None
    prior_observation_time: datetime | None
    prior_value: Decimal | None
    source_version: str | None
    revision_status: str = "revised_history"

    @property
    def prior_return(self) -> Decimal | None:
        if self.latest_value is None or self.prior_value is None or self.prior_value == 0:
            return None
        return self.latest_value / self.prior_value - Decimal("1")


def latest_causal_state(
    observations: Iterable[H10Observation],
    *,
    instrument: str,
    release_at: datetime,
) -> ReleaseState:
    """Return the two latest observations actually available at ``release_at``."""
    eligible = sorted(
        (
            obs
            for obs in observations
            if obs.instrument == instrument
            and obs.usable_at <= release_at
            and obs.event_time <= release_at
        ),
        key=lambda obs: (obs.event_time, obs.usable_at, obs.observation_id),
    )
    if not eligible:
        return ReleaseState(release_at, instrument, None, None, None, None, None)
    latest = eligible[-1]
    prior = eligible[-2] if len(eligible) >= 2 else None
    return ReleaseState(
        release_at=release_at,
        instrument=instrument,
        latest_observation_time=latest.event_time,
        latest_value=latest.value,
        prior_observation_time=prior.event_time if prior else None,
        prior_value=prior.value if prior else None,
        source_version=latest.source_version,
    )


def build_release_states(
    observations: Iterable[H10Observation],
    *,
    release_times: Iterable[datetime],
    instruments: Iterable[str],
) -> list[ReleaseState]:
    """Build a deterministic release-time information panel."""
    rows: list[ReleaseState] = []
    obs = list(observations)
    for release_at in sorted(release_times):
        if release_at.tzinfo is None or release_at.utcoffset() is None:
            raise ValueError("release_at values must be timezone-aware")
        for instrument in instruments:
            rows.append(
                latest_causal_state(
                    obs,
                    instrument=instrument,
                    release_at=release_at,
                )
            )
    return rows


def assert_no_future_information(states: Iterable[ReleaseState]) -> None:
    """Fail closed if an information-set row contains a future observation."""
    for state in states:
        for observation_time in (state.latest_observation_time, state.prior_observation_time):
            if observation_time is not None and observation_time > state.release_at:
                raise AssertionError(
                    f"future observation leaked into release state: {observation_time} > {state.release_at}"
                )
