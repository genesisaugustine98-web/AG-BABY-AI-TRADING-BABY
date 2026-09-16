"""Dependency-free Federal Reserve H.10 daily FX reference-data adapter.

This adapter is intentionally reference-data only. H.10 is not executable bid/ask
market data, so observations are never labeled as execution-grade quotes.
"""
from __future__ import annotations

import csv
import io
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

H10_DAILY_CSV_URL = (
    "https://www.federalreserve.gov/datadownload/DownloadTable.aspx?"
    "filetype=csv&label=include&lastobs=10&layout=seriescolumn&rel=H10&"
    "series=60f32914ab61dfab590e0e470153e3ae&type=package"
)


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


def _parse_decimal(value: str) -> Decimal | None:
    value = value.strip()
    if value in {"", "ND", "N/A", "NA"}:
        return None
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"invalid H10 numeric value: {value!r}") from exc


def parse_h10_daily_csv(payload: str, *, usable_at: datetime | None = None) -> list[H10Observation]:
    """Parse an H.10 daily CSV export into deterministic reference observations."""
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
            day = date.fromisoformat(date_text)
            event_time = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
            observations.append(
                H10Observation(
                    instrument=instrument,
                    event_time=event_time,
                    usable_at=max(usable_at, event_time),
                    value=value,
                    source="Federal Reserve Board H.10",
                    source_version=date_text,
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
