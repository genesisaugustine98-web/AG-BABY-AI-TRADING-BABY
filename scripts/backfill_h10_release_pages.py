"""Reconstruct a point-in-time H.10 archive from dated Federal Reserve release pages."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import re
from datetime import date, datetime, timedelta, time, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

BASE = "https://www.federalreserve.gov/releases/h10/"
NY = ZoneInfo("America/New_York")
RELEASE_TIME = time(16, 15)
MAX_WORKERS = 8
FETCH_TIMEOUT_SECONDS = 15


class H10Parser(HTMLParser):
    """Collect HTML tables as normalized rows."""

    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._table = []
        elif self._table is not None and tag == "tr":
            self._row = []
        elif self._row is not None and tag in {"td", "th"}:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._row is not None and self._cell is not None:
            self._row.append(re.sub(r"\s+", " ", "".join(self._cell)).strip())
            self._cell = None
        elif tag == "tr" and self._table is not None and self._row is not None:
            if self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None


def fetch(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "AG-BABY-research/1.0"})
    with urlopen(req, timeout=FETCH_TIMEOUT_SECONDS) as resp:
        return resp.read()


def release_at(release_date: date) -> datetime:
    return datetime.combine(release_date, RELEASE_TIME, tzinfo=NY).astimezone(timezone.utc)


def candidate_release_dates(start_year: int, end_year: int) -> list[date]:
    """Enumerate Mondays plus Tuesdays for Monday-holiday release shifts.

    H.10 is normally released Monday at 4:15 p.m. Eastern Time; when a Monday
    is a federal holiday, the weekly statistical release moves to Tuesday.
    Fetching both weekdays is simpler and safer than assuming an index page
    enumerates every historical dated release URL.
    """
    start = date(start_year, 1, 1)
    end = date(end_year, 12, 31)
    cursor = start
    dates: list[date] = []
    while cursor <= end:
        if cursor.weekday() in (0, 1):
            dates.append(cursor)
        cursor += timedelta(days=1)
    return dates


def _date_header(value: str) -> tuple[int, int] | None:
    value = value.strip().replace(".", "")
    for fmt in ("%b %d", "%B %d"):
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.month, parsed.day
        except ValueError:
            continue
    return None


def parse_release(html: str, release_date: date) -> list[dict[str, object]]:
    parser = H10Parser()
    parser.feed(html)
    targets = {
        "EMU MEMBERS": "EURUSD_REFERENCE",
        "UNITED KINGDOM": "GBPUSD_REFERENCE",
        "JAPAN": "USDJPY_REFERENCE",
    }
    usable = release_at(release_date)
    observations: list[dict[str, object]] = []

    for table in parser.tables:
        header_idx = next(
            (i for i, row in enumerate(table) if sum(_date_header(cell) is not None for cell in row) >= 2),
            None,
        )
        if header_idx is None:
            continue
        positions: list[tuple[int, date]] = []
        for idx, cell in enumerate(table[header_idx]):
            parsed = _date_header(cell)
            if parsed is None:
                continue
            year = release_date.year
            if release_date.month == 1 and parsed[0] == 12:
                year -= 1
            positions.append((idx, date(year, parsed[0], parsed[1])))

        for row in table[header_idx + 1 :]:
            if len(row) < 3:
                continue
            country = row[0].upper()
            instrument = next((value for key, value in targets.items() if key in country), None)
            if instrument is None:
                continue
            for idx, event_day in positions:
                if idx >= len(row):
                    continue
                raw_value = row[idx].strip()
                if raw_value in {"", "ND", "N/A", "NA"}:
                    continue
                try:
                    value = raw_value.replace(",", "")
                    float(value)
                except ValueError:
                    continue
                observations.append({
                    "instrument": instrument,
                    "event_time": datetime(event_day.year, event_day.month, event_day.day, tzinfo=timezone.utc).isoformat(),
                    "usable_at": usable.isoformat(),
                    "value": value,
                    "source": "Federal Reserve Board H.10 dated release page",
                    "source_version": f"H10-release-{release_date.isoformat()}",
                    "observation_id": f"H10:{instrument}:{event_day.isoformat()}:{release_date.isoformat()}",
                    "execution_grade": False,
                })
    return observations


def _acquire_release(release_date: date) -> tuple[date, bytes, list[dict[str, object]]] | None:
    url = f"{BASE}{release_date:%Y%m%d}/"
    try:
        raw = fetch(url)
    except Exception:
        return None
    parsed = parse_release(raw.decode("utf-8", errors="replace"), release_date)
    if not parsed:
        return None
    return release_date, raw, parsed


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--from-year", type=int, default=2009)
    p.add_argument("--to-year", type=int, default=date.today().year)
    p.add_argument("--output-dir", default="artifacts/h10/vintages")
    args = p.parse_args()
    if args.from_year > args.to_year:
        raise SystemExit("from-year must be <= to-year")

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifests: list[dict[str, object]] = []

    candidates = candidate_release_dates(args.from_year, args.to_year)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(_acquire_release, day) for day in candidates]
        results = [future.result() for future in as_completed(futures)]

    for result in sorted((row for row in results if row is not None), key=lambda row: row[0]):
        release_date, raw, observations = result
        raw_sha = hashlib.sha256(raw).hexdigest()
        stem = release_date.isoformat()
        (out / f"h10_release_{stem}.html").write_bytes(raw)
        with (out / f"h10_release_{stem}.jsonl").open("w", encoding="utf-8") as handle:
            for row in observations:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
        manifests.append({
            "release_date": stem,
            "release_at_utc": release_at(release_date).isoformat(),
            "source_url": f"{BASE}{release_date:%Y%m%d}/",
            "raw_sha256": raw_sha,
            "observation_count": len(observations),
            "revision_status": "point_in_time_release_page",
        })

    (out / "archive_manifest.json").write_text(json.dumps({
        "schema_version": "2",
        "source": "Federal Reserve Board H.10",
        "from_year": args.from_year,
        "to_year": args.to_year,
        "revision_status": "point_in_time_release_page",
        "release_count": len(manifests),
        "candidate_date_count": len(candidates),
        "releases": manifests,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "candidate_date_count": len(candidates),
        "release_count": len(manifests),
        "output_dir": str(out),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
