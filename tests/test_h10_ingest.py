from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from apps.research.h10_ingest import h10_release_timestamp, parse_h10_daily_csv


CSV_FIXTURE = """Series,Description,2026-09-10,2026-09-11
RXI$US_N.B.EU,Euro-Area Euro,1.1572,1.1604
RXI$US_N.B.UK,United Kingdom Pound,1.3532,1.3524
RXI_N.B.JA,Japanese Yen,153.2400,153.7100
RXI$US_N.B.AL,Australian Dollar,0.7171,0.7174
RXI$US_N.B.BAD,Unknown,ND,1.2345
"""


def test_h10_release_timestamp_handles_dst():
    assert h10_release_timestamp(date(2026, 1, 5)) == datetime(2026, 1, 5, 21, 15, tzinfo=timezone.utc)
    assert h10_release_timestamp(date(2026, 9, 14)) == datetime(2026, 9, 14, 20, 15, tzinfo=timezone.utc)


def test_h10_parser_preserves_explicit_historical_availability():
    release = h10_release_timestamp(date(2026, 9, 14))
    observations = parse_h10_daily_csv(CSV_FIXTURE, usable_at=release, source_version="release-2026-09-14")
    assert len(observations) == 9
    euro = next(item for item in observations if item.observation_id == "H10:RXI$US_N.B.EU:2026-09-11")
    assert euro.instrument == "EURUSD_REFERENCE"
    assert euro.value == Decimal("1.1604")
    assert euro.usable_at == release
    assert euro.source_version == "release-2026-09-14"
    assert euro.execution_grade is False


def test_h10_parser_requires_timezone_for_explicit_availability():
    with pytest.raises(ValueError):
        parse_h10_daily_csv(CSV_FIXTURE, usable_at=datetime(2026, 9, 14, 20, 15))


def test_h10_parser_rejects_bad_header_and_date():
    with pytest.raises(ValueError):
        parse_h10_daily_csv("NotSeries,Description,2026-09-10\nRXI$US_N.B.EU,Euro,1.1")
    with pytest.raises(ValueError):
        parse_h10_daily_csv("Series,Description,not-a-date\nRXI$US_N.B.EU,Euro,1.1")
