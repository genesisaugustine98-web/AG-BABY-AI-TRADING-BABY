"""UTC handling for timestamps returned by the MetaTrader 5 Python API.

MetaTrader 5 documents that tick and bar timestamps returned through the Python
integration are UTC epoch values. HFM server time (GMT+2 winter / GMT+3 summer) is a
separate trading-schedule concept and must not be applied again to API timestamps.
Keeping this boundary explicit prevents quote/bar/deal streams from being shifted by
two or three hours and becoming internally inconsistent.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_SERVER_TIMEZONE = "Europe/Athens"
MODERN_EPOCH_MS = 946684800000  # 2000-01-01; retained for compatibility/documentation.


def server_timezone() -> ZoneInfo:
    """Return the configured HFM server timezone for schedule calculations.

    This timezone is not applied to MT5 API epoch timestamps.
    """
    name = os.getenv("MT5_SERVER_TIMEZONE", DEFAULT_SERVER_TIMEZONE).strip()
    if not name:
        name = DEFAULT_SERVER_TIMEZONE
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(f"invalid MT5_SERVER_TIMEZONE:{name}") from exc


def broker_server_epoch_ms_to_utc_ms(timestamp_ms: int, *, tz: ZoneInfo | None = None) -> int:
    """Validate and return an MT5 API epoch-ms timestamp as UTC.

    tz remains accepted for backwards compatibility with earlier callers, but it is
    intentionally ignored because MetaTrader 5 returns tick/bar timestamps in UTC.
    """
    del tz
    raw = int(timestamp_ms)
    if raw <= 0:
        raise ValueError("timestamp_ms must be positive")
    return raw


def broker_server_epoch_seconds_to_utc_ms(timestamp_seconds: int, *, tz: ZoneInfo | None = None) -> int:
    """Validate and convert an MT5 API epoch-seconds timestamp to UTC milliseconds."""
    del tz
    raw_seconds = int(timestamp_seconds)
    if raw_seconds <= 0:
        raise ValueError("timestamp_seconds must be positive")
    return raw_seconds * 1000


def utc_iso_from_broker_epoch_ms(timestamp_ms: int, *, tz: ZoneInfo | None = None) -> str:
    normalized = broker_server_epoch_ms_to_utc_ms(timestamp_ms, tz=tz)
    return datetime.fromtimestamp(normalized / 1000, tz=timezone.utc).isoformat()


def utc_now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


__all__ = [
    "DEFAULT_SERVER_TIMEZONE",
    "MODERN_EPOCH_MS",
    "broker_server_epoch_ms_to_utc_ms",
    "broker_server_epoch_seconds_to_utc_ms",
    "server_timezone",
    "utc_iso_from_broker_epoch_ms",
    "utc_now_ms",
]
