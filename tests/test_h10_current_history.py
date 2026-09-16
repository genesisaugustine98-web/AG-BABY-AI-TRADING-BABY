from datetime import datetime, timezone
from decimal import Decimal

from apps.research.h10_current_history import parse_current_history_with_schedule


def test_assigns_following_release_schedule_without_calling_values_real_time_vintage():
    payload = """Series,Description,2026-09-11
RXI$US_N.B.EU,Euro-Area Euro,1.1604
"""
    rows = parse_current_history_with_schedule(payload)
    assert len(rows) == 1
    row = rows[0]
    assert row.event_time == datetime(2026, 9, 11, tzinfo=timezone.utc)
    assert row.usable_at == datetime(2026, 9, 14, 20, 15, tzinfo=timezone.utc)
    assert row.value == Decimal("1.1604")
    assert row.execution_grade is False
    assert "current-history-retrieved-snapshot" in row.source_version
