"""Research governance: fixed hypotheses, evidence records, and negative knowledge."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from typing import Literal

Outcome = Literal["supported", "not_supported", "inconclusive"]


@dataclass(frozen=True)
class Hypothesis:
    hypothesis_id: str
    statement: str
    rule: str
    instruments: tuple[str, ...]
    horizons: tuple[int, ...]
    development_fraction: Decimal
    validation_fraction: Decimal
    holdout_fraction: Decimal

    def validate(self) -> None:
        if not self.hypothesis_id or not self.statement or not self.rule:
            raise ValueError("hypothesis metadata is incomplete")
        if not self.instruments or any(h < 1 for h in self.horizons):
            raise ValueError("hypothesis instruments/horizons are invalid")
        total = self.development_fraction + self.validation_fraction + self.holdout_fraction
        if total != Decimal("1"):
            raise ValueError("split fractions must sum to 1")
        if min(self.development_fraction, self.validation_fraction, self.holdout_fraction) <= 0:
            raise ValueError("split fractions must all be positive")


@dataclass(frozen=True)
class EvidenceRecord:
    hypothesis_id: str
    sample_start: str
    sample_end: str
    split: str
    instrument: str
    horizon: int
    one_way_cost_bps: Decimal
    n: int
    mean_net: Decimal | None
    cumulative_net: Decimal | None
    max_drawdown: Decimal | None
    outcome: Outcome
    dataset_revision_status: str

    def to_jsonable(self) -> dict[str, object]:
        row = asdict(self)
        for key in ("one_way_cost_bps", "mean_net", "cumulative_net", "max_drawdown"):
            if row[key] is not None:
                row[key] = str(row[key])
        return row


def canonical_hash(record: EvidenceRecord) -> str:
    payload = json.dumps(record.to_jsonable(), sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def append_negative_knowledge(path: str | Path, record: EvidenceRecord, reason: str) -> None:
    """Append a durable failure/inconclusive record; never overwrite prior evidence."""
    if record.outcome not in {"not_supported", "inconclusive"}:
        raise ValueError("negative knowledge requires a failed or inconclusive outcome")
    payload = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "record_hash": canonical_hash(record),
        "reason": reason,
        "evidence": record.to_jsonable(),
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
