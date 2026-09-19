from datetime import datetime, timezone

from apps.execution_gateway.mt5_time import (
    broker_server_epoch_ms_to_utc_ms,
    broker_server_epoch_seconds_to_utc_ms,
    utc_iso_from_broker_epoch_ms,
)


def _epoch_ms(value: str) -> int:
    return int(datetime.fromisoformat(value).timestamp() * 1000)


def test_hfm_summer_server_time_normalizes_three_hours_back_to_utc():
    raw = _epoch_ms("2026-09-19T14:26:02+00:00")
    normalized = broker_server_epoch_ms_to_utc_ms(raw)
    assert normalized == _epoch_ms("2026-09-19T11:26:02+00:00")
    assert utc_iso_from_broker_epoch_ms(raw).startswith("2026-09-19T11:26:02+00:00")


def test_hfm_winter_server_time_normalizes_two_hours_back_to_utc():
    raw = _epoch_ms("2026-12-19T14:26:02+00:00")
    normalized = broker_server_epoch_ms_to_utc_ms(raw)
    assert normalized == _epoch_ms("2026-12-19T12:26:02+00:00")


def test_seconds_and_milliseconds_paths_match():
    raw_ms = _epoch_ms("2026-09-19T14:26:02+00:00")
    assert broker_server_epoch_seconds_to_utc_ms(raw_ms // 1000) == raw_ms - 3 * 60 * 60 * 1000
