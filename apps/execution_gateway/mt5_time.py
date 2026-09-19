"""Time normalization for broker-local MT5 timestamps.

The HFM MT5 terminal observed in the demo environment returns tick/deal epoch values
whose wall-clock interpretation follows HFM server time (GMT+3 during summer and GMT+2
during winter), rather than the machine's UTC clock. Treat broker timestamps as broker
wall-clock values until explicitly normalized here.

The timezone is configurable with MT5_SERVER_TIMEZONE and defaults to Europe/Athens,
whose EET/EEST UTC-offset schedule matches the documented HFM server schedule. The
raw broker timestamp remains available to audit callers; internal freshness and
checkpoint calculations must use the normalized UTC millisecond value.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_SERVER_TIMEZONE = "Europe/Athens"


def server_timezone() -> ZoneInfo:
    name = os.getenv("MT5_SERVER_TIMEZONE", DEFAULT_SERVER_TIMEZONE).strip()
    if not name:
        name = DEFAULT_SERVER_TIMEZONE
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(f"invalid MT5_SERVER_TIMEZONE:{name}") from exc


def broker_server_epoch_ms_to_utc_ms(timestamp_ms: int, *, tz: ZoneInfo | None = None) -> int:
    """Interpret an MT5 epoch-ms value as broker-local wall time and normalize to UTC.

    MT5/HFM supplies a numeric epoch that is three hours ahead of the observed machine
    UTC clock in summer. Converting by simply attaching UTC therefore produces future
    timestamps. We first decode the numeric value as a broker-local wall-clock reading,
    then attach the broker timezone and convert to UTC.
    """
    raw = int(timestamp_ms)
    if raw <= 0:
        raise ValueError("timestamp_ms must be positive")
    zone = tz or server_timezone()
    broker_wall = datetime.fromtimestamp(raw / 1000, tz=timezone.utc).replace(tzinfo=None)
    aware = broker_wall.replace(tzinfo=zone)
    return int(aware.astimezone(timezone.utc).timestamp() * 1000)


def broker_server_epoch_seconds_to_utc_ms(timestamp_seconds: int, *, tz: ZoneInfo | None = None) -> int:
    return broker_server_epoch_ms_to_utc_ms(int(timestamp_seconds) * 1000, tz=tz)


def utc_iso_from_broker_epoch_ms(timestamp_ms: int, *, tz: ZoneInfo | None = None) -> str:
    normalized = broker_server_epoch_ms_to_utc_ms(timestamp_ms, tz=tz)
    return datetime.fromtimestamp(normalized / 1000, tz=timezone.utc).isoformat()


def utc_now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


__all__ = [
    "DEFAULT_SERVER_TIMEZONE",
    "broker_server_epoch_ms_to_utc_ms",
    "broker_server_epoch_seconds_to_utc_ms",
    "server_timezone",
    "utc_iso_from_broker_epoch_ms",
    "utc_now_ms",
]
