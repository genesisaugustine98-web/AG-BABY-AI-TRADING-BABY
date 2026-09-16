"""Dependency-free Federal Reserve H.10 daily FX reference-data adapter.

This adapter is intentionally reference-data only. H.10 is not executable bid/ask
market data, so observations are never labeled as execution-grade quotes.
"""
from __future__ import annotations

import csv
import io
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

H10_DAILY_CSV_URL = (
    "https://www.federalreserve.gov/datadownload/DownloadTable.aspx?"
    "filetype=csv&label=include&lastobs=10&layout=seriescolumn&rel=H10&"
    "series=60f32914ab61dfab590e0e470153e3ae&type=package"
)
H10_RELEASE_TIME_ET = time(16, 15)
H10_NEW_YORK = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class H10Observation:
    instrument: str
    event_time: datetime
    usable_at: datetime
    value: Decimal
    source: str
    source_version: str
    observation_id: str
    execution_grade: bool = False


def h10_release_timestamp(release_date: date) -> datetime:
    """Return the published H.10 release timestamp in UTC for a known release date.

    The caller supplies the actual release date, including holiday-shifted releases.
    America/New_York handles EST/EDT transitions without hard-coded offsets.
    """
    local = datetime.combine(release_date, H10_RELEASE_TIME_ET, tzinfo=H10_NEW_YORK)
    return local.astimezone(timezone.utc)


def _parse_decimal(value: str) -> Decimal | None:
    value = value.strip()
    if value in {"", "ND", "N/A", "NA"}:
        return None
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"invalid H10 numeric value: {value!r}") from exc


def parse_h10_daily_csv(
    payload: str,
    *,
    usable_at: datetime | None = None,
    source_version: str = "H10-daily-csv",
) -> list[H10Observation]:
    """Parse an H.10 daily CSV export into deterministic reference observations.

    For historical replay, pass the actual H.10 release timestamp as ``usable_at``.
    Leaving it unset is appropriate only for live ingestion and stamps the batch with
    current UTC time, never an inferred historical publication time.
    """
    if usable_at is None:
        usable_at = datetime.now(timezone.utc)
    elif usable_at.tzinfo is None or usable_at.utcoffset() is None:
        raise ValueError("usable_at must be timezone-aware")

    reader = csv.reader(io.StringIO(payload))
    rows = [row for row in reader if row]
    header_index = next((i for i, row in enumerate(rows) if row and row[0].strip() == "Series"), None)
    if header_index is None:
        raise ValueError("H10 CSV header not found")

    header = [cell.strip() for cell in rows[header_index]]
    date_columns = [(idx, cell) for idx, cell in enumerate(header[2:], start=2) if cell]
    observations: list[H10Observation] = []

    for row in rows[header_index + 1:]:
        if len(row) < 3:
            continue
        series = row[0].strip()
        description = row[1].strip() if len(row) > 1 else ""
        if not series or not series.startswith("RX"):
            continue
        instrument = _instrument_from_description(description, series)
        for idx, date_text in date_columns:
            if idx >= len(row):
                continue
            value = _parse_decimal(row[idx])
            if value is None:
                continue
            try:
                day = date.fromisoformat(date_text)
            except ValueError as exc:
                raise ValueError(f"invalid H10 date column: {date_text!r}") from exc
            event_time = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
            observations.append(
                H10Observation(
                    instrument=instrument,
                    event_time=event_time,
                    usable_at=usable_at,
                    value=value,
                    source="Federal Reserve Board H.10",
                    source_version=source_version,
                    observation_id=f"H10:{series}:{date_text}",
                )
            )
    return observations


def _instrument_from_description(description: str, series: str) -> str:
    text = description.lower()
    if "euro" in text or series.endswith("EU"):
        return "EURUSD_REFERENCE"
    if "pound" in text or series.endswith("UK"):
        return "GBPUSD_REFERENCE"
    if "yen" in text or series.endswith("JA"):
        return "USDJPY_REFERENCE"
    return f"H10:{series}"


def fetch_h10_daily_csv(url: str = H10_DAILY_CSV_URL, *, timeout_seconds: int = 20) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "AG-BABY-research/1.0"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return response.read().decode("utf-8-sig")
