"""Turn research evidence into a machine-readable, reviewable report."""
from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
import json
from pathlib import Path
from typing import Iterable

from .evidence_engine import EvidenceStats


def _jsonify(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _jsonify(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonify(v) for v in value]
    return value


def build_evidence_row(
    *,
    hypothesis_id: str,
    instrument: str,
    horizon: int,
    one_way_cost_bps: Decimal,
    split: str,
    status: str,
    reason: str,
    stats: EvidenceStats,
    dataset_revision_status: str,
) -> dict[str, object]:
    row = {
        "hypothesis_id": hypothesis_id,
        "instrument": instrument,
        "horizon": horizon,
        "one_way_cost_bps": one_way_cost_bps,
        "split": split,
        "status": status,
        "reason": reason,
        "dataset_revision_status": dataset_revision_status,
        "stats": asdict(stats),
    }
    return _jsonify(row)


def write_jsonl(rows: Iterable[dict[str, object]], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
