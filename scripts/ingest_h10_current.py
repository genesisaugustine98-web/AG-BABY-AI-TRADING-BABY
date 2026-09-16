"""Fetch the current Federal Reserve H.10 daily FX package and emit a raw+normalized snapshot.

The script discovers the actual current H.10 release date from the Federal Reserve
current-release page, then stamps every observation with that publication time.
This avoids backtest leakage from assigning the observation date as availability.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from apps.research.h10_ingest import (
    H10_DAILY_CSV_URL,
    fetch_h10_daily_csv,
    h10_release_timestamp,
    parse_h10_daily_csv,
)

H10_CURRENT_URL = "https://www.federalreserve.gov/releases/h10/current/"


def fetch_current_release_date(*, timeout_seconds: int = 20):
    request = Request(H10_CURRENT_URL, headers={"User-Agent": "AG-BABY-research/1.0"})
    with urlopen(request, timeout=timeout_seconds) as response:
        html = response.read().decode("utf-8", errors="replace")
    match = re.search(r"Release Date:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})", html)
    if not match:
        raise RuntimeError("could not identify current H.10 release date")
    return datetime.strptime(match.group(1), "%B %d, %Y").date()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="artifacts/h10")
    args = parser.parse_args()

    release_date = fetch_current_release_date()
    release_at = h10_release_timestamp(release_date)
    raw_csv = fetch_h10_daily_csv()
    raw_bytes = raw_csv.encode("utf-8")
    raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    observations = parse_h10_daily_csv(
        raw_csv,
        usable_at=release_at,
        source_version=f"H10-release-{release_date.isoformat()}",
    )

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"h10_{release_date.isoformat()}"
    raw_path = out / f"{stem}.csv"
    normalized_path = out / f"{stem}.jsonl"
    manifest_path = out / f"{stem}.manifest.json"

    raw_path.write_bytes(raw_bytes)
    with normalized_path.open("w", encoding="utf-8") as handle:
        for observation in observations:
            handle.write(
                json.dumps(
                    {
                        "instrument": observation.instrument,
                        "event_time": observation.event_time.isoformat(),
                        "usable_at": observation.usable_at.isoformat(),
                        "value": str(observation.value),
                        "source": observation.source,
                        "source_version": observation.source_version,
                        "observation_id": observation.observation_id,
                        "execution_grade": observation.execution_grade,
                    },
                    sort_keys=True,
                )
                + "\n"
            )

    manifest = {
        "schema_version": "1",
        "source": "Federal Reserve Board H.10",
        "release_date": release_date.isoformat(),
        "release_at_utc": release_at.isoformat(),
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_url": H10_DAILY_CSV_URL,
        "current_release_url": H10_CURRENT_URL,
        "raw_sha256": raw_sha256,
        "observation_count": len(observations),
        "execution_grade": False,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
