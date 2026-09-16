"""Acquire current H.10 history and run a fixed, revision-aware experiment."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from apps.research.experiment_runner import ResearchSplit, run_fixed_grid
from apps.research.h10_current_history import parse_current_history_with_schedule

BASE_URL = "https://www.federalreserve.gov/datadownload/Download.aspx"
SERIES_PACKAGE = "60f32914ab61dfab590e0e470153e3ae"


def fetch_history(start: date, end: date, timeout_seconds: int = 60) -> bytes:
    params = {
        "filetype": "csv",
        "from": start.strftime("%m/%d/%Y"),
        "to": end.strftime("%m/%d/%Y"),
        "label": "include",
        "layout": "seriescolumn",
        "rel": "H10",
        "series": SERIES_PACKAGE,
        "type": "package",
    }
    url = BASE_URL + "?" + urlencode(params)
    request = Request(url, headers={"User-Agent": "AG-BABY-research/1.0"})
    with urlopen(request, timeout=timeout_seconds) as response:
        return response.read()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-date", default="2000-01-01")
    parser.add_argument("--to-date", default="2026-09-11")
    parser.add_argument("--output-dir", default="artifacts/research")
    args = parser.parse_args()

    start = date.fromisoformat(args.from_date)
    end = date.fromisoformat(args.to_date)
    payload = fetch_history(start, end)
    source_sha = hashlib.sha256(payload).hexdigest()
    raw_text = payload.decode("utf-8-sig")
    observations = parse_current_history_with_schedule(raw_text)

    instruments = ["EURUSD_REFERENCE", "GBPUSD_REFERENCE", "USDJPY_REFERENCE"]
    split = ResearchSplit(date(2018, 12, 31), date(2022, 12, 31))
    rows = run_fixed_grid(observations, instruments=instruments, split=split)

    report = {
        "schema_version": "1",
        "experiment": "h10_current_history_fixed_grid_v1",
        "status": "schedule_correct_but_revised_history",
        "interpretation_warning": "Values are current Federal Reserve historical values and may include later revisions; availability is assigned from the documented H.10 release schedule.",
        "source_sha256": source_sha,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "from_date": start.isoformat(),
        "to_date": end.isoformat(),
        "instrument_scope": instruments,
        "split": {
            "development_end": "2018-12-31",
            "validation_end": "2022-12-31",
            "holdout": "2023-01-01 onward",
        },
        "fixed_design": {
            "rules": ["momentum", "reversal"],
            "horizons": [1, 5],
            "one_way_cost_bps": ["0", "2", "5", "10"],
            "parameter_selection": "none",
        },
        "observation_count": len(observations),
        "results": rows,
    }

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "h10_current_history.csv").write_bytes(payload)
    (out / "h10_current_history_experiment.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: report[k] for k in ("experiment", "status", "source_sha256", "observation_count", "split")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
