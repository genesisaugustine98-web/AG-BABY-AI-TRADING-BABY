from datetime import date

from apps.research.h10_vintage import h10_release_date_for_observation


def test_normal_week_releases_next_monday():
    assert h10_release_date_for_observation(date(2026, 9, 11)) == date(2026, 9, 14)


def test_labor_day_week_shifts_to_tuesday():
    assert h10_release_date_for_observation(date(2026, 9, 4)) == date(2026, 9, 8)


def test_juneteenth_shift_when_monday_observed():
    assert h10_release_date_for_observation(date(2021, 6, 18)) == date(2021, 6, 21)
