"""Historical H.10 release-vintage assignment.

H.10 publishes daily bilateral exchange rates for the previous business week.
The regular release is Monday at 16:15 America/New_York; when Monday is a
Federal holiday, publication shifts to the following business day. This module
assigns the release date deterministically for ordinary historical weeks.
"""
from __future__ import annotations

from datetime import date, timedelta
from calendar import monthrange


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    day = 1
    first = date(year, month, day)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    last = date(year, month, monthrange(year, month)[1])
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _observed_fixed(year: int, month: int, day: int) -> date:
    actual = date(year, month, day)
    if actual.weekday() == 5:
        return actual - timedelta(days=1)
    if actual.weekday() == 6:
        return actual + timedelta(days=1)
    return actual


def monday_federal_holidays(year: int) -> set[date]:
    holidays = {
        _observed_fixed(year, 1, 1),                 # New Year's Day
        _nth_weekday(year, 1, 0, 3),                 # MLK Day
        _nth_weekday(year, 2, 0, 3),                 # Washington's Birthday
        _last_weekday(year, 5, 0),                   # Memorial Day
        _observed_fixed(year, 6, 19),                # Juneteenth
        _observed_fixed(year, 7, 4),                 # Independence Day
        _nth_weekday(year, 9, 0, 1),                 # Labor Day
        _nth_weekday(year, 10, 0, 2),                # Columbus/Indigenous Peoples Day
        _observed_fixed(year, 11, 11),               # Veterans Day
        _observed_fixed(year, 12, 25),               # Christmas Day
    }
    return {d for d in holidays if d.weekday() == 0}


def h10_release_date_for_observation(observation_date: date) -> date:
    """Return the H.10 release date for an observation in the previous business week."""
    monday = observation_date - timedelta(days=observation_date.weekday())
    release = monday + timedelta(days=7)
    # For Mon-Fri observations, the following week's Monday is the normal release.
    if release in monday_federal_holidays(release.year):
        return release + timedelta(days=1)
    return release
