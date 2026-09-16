"""Reproducible historical H.10 acquisition with explicit release-vintage metadata."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from apps.research.h10_ingest import h10_release_timestamp, parse_h10_daily_csv

BASE_DOWNLOAD_URL = "https://www.federalreserve.gov/datadownload/Download.aspx"
H10_SERIES_PACKAGE = "60f32914ab61dfab590e0e470153e3ae"


def build_historical_url(start: date, end: date) -> str:
    params = {
        "filetype": "csv",
        "from": start.strftime("%m/%d/%Y"),
        "to": end.strftime("%m/%d/%Y"),
        "label": "include",
        "layout": "seriescolumn",
        "rel": "H10",
        "series": H10_SERIES_PACKAGE,
    }
    return BASE_DOWNLOAD_URL + "?" + urlencode(params)


def fetch_text(url: str, timeout_seconds: int = 30) -> str:
    request = Request(url, headers={"User-Agent": "AG-BABY-research/1.0"})
    with urlopen(request, timeout=timeout_seconds) as response:
        return response.read().decode("utf-8-sig")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-date", required=True)
    parser.add_argument("--to-date", required=True)
    parser.add_argument("--release-date", required=True)
    parser.add_argument("--output-dir", default="artifacts/h10/historical")
    args = parser.parse_args()

    start = date.fromisoformat(args.from_date)
    end = date.fromisoformat(args.to_date)
    release_date = date.fromisoformat(args.release_date)
    if start > end:
        raise SystemExit("from-date must be <= to-date")

    url = build_historical_url(start, end)
    raw = fetch_text(url)
    release_at = h10_release_timestamp(release_date)
    observations = parse_h10_daily_csv(
        raw,
        usable_at=release_at,
        source_version=f"H10-release-{release_date.isoformat()}",
    )

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"h10_{start.isoformat()}_{end.isoformat()}_release_{release_date.isoformat()}"
    raw_path = out / f"{stem}.csv"
    normalized_path = out / f"{stem}.jsonl"
    manifest_path = out / f"{stem}.manifest.json"

    raw_bytes = raw.encode("utf-8")
    raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    raw_path.write_bytes(raw_bytes)
    with normalized_path.open("w", encoding="utf-8") as handle:
        for obs in observations:
            handle.write(json.dumps({
                "instrument": obs.instrument,
                "event_time": obs.event_time.isoformat(),
                "usable_at": obs.usable_at.isoformat(),
                "value": str(obs.value),
                "source": obs.source,
                "source_version": obs.source_version,
                "observation_id": obs.observation_id,
                "execution_grade": obs.execution_grade,
            }, sort_keys=True) + "\n")

    manifest = {
        "schema_version": "1",
        "source": "Federal Reserve Board H.10",
        "from_date": start.isoformat(),
        "to_date": end.isoformat(),
        "release_date": release_date.isoformat(),
        "release_at_utc": release_at.isoformat(),
        "source_url": url,
        "raw_sha256": raw_sha256,
        "observation_count": len(observations),
        "execution_grade": False,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
