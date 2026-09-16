"""Reconstruct a point-in-time H.10 archive from dated Federal Reserve release pages.

The current DDP history is revised history. This script instead discovers dated H.10
release pages and preserves each publication timestamp as the information-availability
clock. It intentionally extracts only the EUR, GBP, and JPY rows used by the fixed
research battery.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date, datetime, time, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

BASE = "https://www.federalreserve.gov/releases/h10/"
NY = ZoneInfo("America/New_York")
RELEASE_TIME = time(16, 15)


class H10Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_table = False
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self.in_table = True
        elif self.in_table and tag in {"tr"}:
            self._row = []
        elif self.in_table and tag in {"td", "th"}:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self.in_table and self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.in_table and tag in {"td", "th"} and self._cell is not None:
            text = re.sub(r"\s+", " ", "".join(self._cell)).strip()
            if self._row is not None:
                self._row.append(text)
            self._cell = None
        elif self.in_table and tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
        elif tag == "table":
            self.in_table = False


def fetch(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "AG-BABY-research/1.0"})
    with urlopen(req, timeout=30) as resp:
        return resp.read()


def release_at(release_date: date) -> datetime:
    return datetime.combine(release_date, RELEASE_TIME, tzinfo=NY).astimezone(timezone.utc)


def discover_release_dates(start_year: int, end_year: int) -> list[date]:
    dates: list[date] = []
    for year in range(start_year, end_year + 1):
        url = f"{BASE}{year}/"
        try:
            html = fetch(url).decode("utf-8", errors="replace")
        except Exception:
            continue
        # Dated release links such as /releases/h10/20211227/
        for match in re.finditer(r"/releases/h10/(\d{8})/", html, flags=re.I):
            text = match.group(1)
            try:
                dates.append(datetime.strptime(text, "%Y%m%d").date())
            except ValueError:
                pass
    return sorted(set(dates))


def parse_release(html: str, release_date: date) -> list[dict[str, object]]:
    parser = H10Parser()
    parser.feed(html)
    rows = parser.rows
    target_rows: dict[str, list[str]] = {}
    for row in rows:
        joined = " ".join(row).upper()
        if "EMU MEMBERS" in joined and "EURO" in joined:
            target_rows["EURUSD_REFERENCE"] = row
        elif "UNITED KINGDOM" in joined and "POUND" in joined:
            target_rows["GBPUSD_REFERENCE"] = row
        elif "JAPAN" in joined and "YEN" in joined:
            target_rows["USDJPY_REFERENCE"] = row

    out: list[dict[str, object]] = []
    usable = release_at(release_date)
    for instrument, row in sorted(target_rows.items()):
        # Country, currency, then daily values. Date headers are extracted from the
        # same release page separately, so row-position parsing is deterministic.
        out.append({
            "instrument": instrument,
            "release_date": release_date.isoformat(),
            "usable_at": usable.isoformat(),
            "raw_row": row,
        })
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--from-year", type=int, default=2009)
    p.add_argument("--to-year", type=int, default=date.today().year)
    p.add_argument("--output-dir", default="artifacts/h10/vintages")
    args = p.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifests: list[dict[str, object]] = []
    for release_date in discover_release_dates(args.from_year, args.to_year):
        url = f"{BASE}{release_date:%Y%m%d}/"
        try:
            raw = fetch(url)
        except Exception:
            continue
        raw_sha = hashlib.sha256(raw).hexdigest()
        parsed = parse_release(raw.decode("utf-8", errors="replace"), release_date)
        if not parsed:
            continue
        stem = release_date.isoformat()
        raw_path = out / f"h10_release_{stem}.html"
        json_path = out / f"h10_release_{stem}.json"
        raw_path.write_bytes(raw)
        json_path.write_text(json.dumps({
            "schema_version": "1",
            "source": "Federal Reserve Board H.10 dated release page",
            "release_date": stem,
            "release_at_utc": release_at(release_date).isoformat(),
            "source_url": url,
            "raw_sha256": raw_sha,
            "revision_status": "point_in_time_release_page",
            "rows": parsed,
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifests.append({
            "release_date": stem,
            "release_at_utc": release_at(release_date).isoformat(),
            "source_url": url,
            "raw_sha256": raw_sha,
            "observation_row_count": len(parsed),
        })

    (out / "archive_manifest.json").write_text(json.dumps({
        "schema_version": "1",
        "source": "Federal Reserve Board H.10",
        "from_year": args.from_year,
        "to_year": args.to_year,
        "revision_status": "point_in_time_release_page",
        "release_count": len(manifests),
        "releases": manifests,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"release_count": len(manifests), "output_dir": str(out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
