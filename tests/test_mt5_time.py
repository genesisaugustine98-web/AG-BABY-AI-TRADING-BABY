from datetime import datetime, timezone

from apps.execution_gateway.mt5_time import (
    broker_server_epoch_ms_to_utc_ms,
    broker_server_epoch_seconds_to_utc_ms,
    utc_iso_from_broker_epoch_ms,
)


def _epoch_ms(value: str) -> int:
    return int(datetime.fromisoformat(value).timestamp() * 1000)


def test_mt5_api_timestamp_is_preserved_as_utc_in_summer():
    raw = _epoch_ms("2026-09-19T14:26:02+00:00")
    normalized = broker_server_epoch_ms_to_utc_ms(raw)
    assert normalized == raw
    assert utc_iso_from_broker_epoch_ms(raw).startswith("2026-09-19T14:26:02+00:00")


def test_mt5_api_timestamp_is_preserved_as_utc_in_winter():
    raw = _epoch_ms("2026-12-19T14:26:02+00:00")
    normalized = broker_server_epoch_ms_to_utc_ms(raw)
    assert normalized == raw


def test_seconds_and_milliseconds_paths_match():
    raw_ms = _epoch_ms("2026-09-19T14:26:02+00:00")
    assert broker_server_epoch_seconds_to_utc_ms(raw_ms // 1000) == raw_ms
