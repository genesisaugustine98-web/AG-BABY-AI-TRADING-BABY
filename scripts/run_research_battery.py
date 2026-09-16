"""CLI for running the fixed research battery against a normalized JSONL dataset."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from apps.research.battery_runner import load_h10_jsonl, run_battery, write_results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="Normalized H.10 JSONL input")
    parser.add_argument("--config", default="configs/research_battery.json")
    parser.add_argument("--output", default="artifacts/research_battery/results.jsonl")
    args = parser.parse_args()

    observations = load_h10_jsonl(args.data)
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    results = run_battery(observations, config=config)
    write_results(results, args.output)

    counts: dict[str, int] = {}
    for row in results:
        counts[row.status] = counts.get(row.status, 0) + 1
    print(json.dumps({"rows": len(results), "status_counts": counts, "output": args.output}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
