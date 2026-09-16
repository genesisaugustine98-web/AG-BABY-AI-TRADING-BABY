"""Run the predeclared H.10 reference-rate experiment grid."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from apps.research.experiment_runner import ResearchSplit, run_fixed_grid
from apps.research.h10_ingest import H10Observation, parse_h10_daily_csv


def load_jsonl(path: Path) -> list[H10Observation]:
    rows: list[H10Observation] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        rows.append(
            H10Observation(
                instrument=item["instrument"],
                event_time=__import__("datetime").datetime.fromisoformat(item["event_time"]),
                usable_at=__import__("datetime").datetime.fromisoformat(item["usable_at"]),
                value=Decimal(item["value"]),
                source=item["source"],
                source_version=item["source_version"],
                observation_id=item["observation_id"],
                execution_grade=bool(item["execution_grade"]),
            )
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="normalized H.10 JSONL")
    parser.add_argument("--output", default="artifacts/research/reference_experiment.json")
    parser.add_argument("--development-end", required=True)
    parser.add_argument("--validation-end", required=True)
    args = parser.parse_args()

    source_path = Path(args.input)
    observations = load_jsonl(source_path)
    source_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    instruments = sorted({item.instrument for item in observations if item.execution_grade is False})
    observations = [item for item in observations if item.execution_grade is False]

    split = ResearchSplit(
        development_end=date.fromisoformat(args.development_end),
        validation_end=date.fromisoformat(args.validation_end),
    )
    rows = run_fixed_grid(observations, instruments=instruments, split=split)
    report = {
        "schema_version": "1",
        "experiment": "h10_reference_fixed_grid_v1",
        "input_sha256": source_digest,
        "observations": len(observations),
        "instruments": instruments,
        "split": {
            "development_end": args.development_end,
            "validation_end": args.validation_end,
            "holdout": "strictly_after_validation_end",
        },
        "fixed_design": {
            "rules": ["momentum", "reversal"],
            "horizons": [1, 5],
            "one_way_cost_bps": ["0", "2", "5", "10"],
            "execution_grade_required": False,
        },
        "results": rows,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("schema_version", "experiment", "input_sha256", "observations", "instruments", "split")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
