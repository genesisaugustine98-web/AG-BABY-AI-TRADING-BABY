"""Deterministic descriptive analysis for a normalized H.10 snapshot.

This is a diagnostic baseline, not an alpha claim. It reports simple one-day
reference-rate changes and cost sensitivity. H.10 remains reference data only.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path


def load_rows(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("--cost-bps", type=Decimal, default=Decimal("0"))
    args = parser.parse_args()

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in load_rows(args.jsonl):
        if row.get("execution_grade"):
            raise ValueError("H.10 observations must not be execution-grade")
        grouped[row["instrument"]].append(row)

    output = {
        "schema_version": "1",
        "analysis": "one_day_reference_return_diagnostics",
        "cost_bps": str(args.cost_bps),
        "execution_grade": False,
        "instruments": {},
    }

    for instrument, rows in sorted(grouped.items()):
        rows.sort(key=lambda r: r["event_time"])
        returns = []
        for previous, current in zip(rows, rows[1:]):
            p0 = Decimal(previous["value"])
            p1 = Decimal(current["value"])
            if p0 <= 0 or p1 <= 0:
                raise ValueError(f"non-positive H.10 value for {instrument}")
            returns.append((p1 / p0) - Decimal("1"))
        net_returns = [r - (args.cost_bps / Decimal("10000")) for r in returns]
        output["instruments"][instrument] = {
            "observations": len(rows),
            "return_observations": len(returns),
            "mean_return": str(sum(returns, Decimal("0")) / len(returns)) if returns else None,
            "mean_net_return": str(sum(net_returns, Decimal("0")) / len(net_returns)) if net_returns else None,
            "positive_fraction": str(
                Decimal(sum(1 for r in returns if r > 0)) / Decimal(len(returns))
            ) if returns else None,
            "start_event_time": rows[0]["event_time"] if rows else None,
            "end_event_time": rows[-1]["event_time"] if rows else None,
        }

    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
