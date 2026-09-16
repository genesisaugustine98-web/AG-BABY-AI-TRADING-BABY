"""Causal research-battery execution for point-in-time reference FX observations.

This runner is deliberately conservative.  It does not reinterpret H.10 reference
rates as executable market data and it refuses a cell when the proposed decision
observation was not actually usable at the decision time.  That distinction prevents
revised historical files from silently becoming look-ahead-biased backtests.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import json
from pathlib import Path
from typing import Iterable

from .h10_ingest import H10Observation
from .reference_backtest import run_reference_backtest, summarize_reference_trades


@dataclass(frozen=True)
class BatteryCell:
    hypothesis_id: str
    rule: str
    instrument: str
    horizon: int
    one_way_cost_bps: Decimal
    split: str


@dataclass(frozen=True)
class BatteryResult:
    cell: BatteryCell
    status: str
    reason: str
    sample_start: str | None
    sample_end: str | None
    summary: dict[str, object] | None


def load_h10_jsonl(path: str | Path) -> list[H10Observation]:
    """Load normalized H.10 observations emitted by the ingestion scripts."""
    from datetime import datetime

    rows: list[H10Observation] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            raw = json.loads(line)
            rows.append(
                H10Observation(
                    instrument=raw["instrument"],
                    event_time=datetime.fromisoformat(raw["event_time"]),
                    usable_at=datetime.fromisoformat(raw["usable_at"]),
                    value=Decimal(raw["value"]),
                    source=raw["source"],
                    source_version=raw["source_version"],
                    observation_id=raw["observation_id"],
                    execution_grade=bool(raw.get("execution_grade", False)),
                )
            )
    return rows


def _split_bounds(series: list[H10Observation], development: Decimal, validation: Decimal, holdout: Decimal) -> dict[str, tuple[int, int]]:
    n = len(series)
    if n < 3:
        return {}
    dev_end = int(n * development)
    val_end = dev_end + int(n * validation)
    if dev_end <= 0 or val_end <= dev_end or val_end >= n:
        return {}
    return {
        "development": (0, dev_end),
        "validation": (dev_end, val_end),
        "holdout": (val_end, n),
    }


def _causal_ready(series: list[H10Observation], horizon: int) -> tuple[bool, str]:
    """Check the first signal observation and forward target for causal availability."""
    if len(series) < horizon + 2:
        return False, "insufficient observations for requested horizon"
    current = series[1]
    previous = series[0]
    target = series[1 + horizon]
    if previous.usable_at > current.event_time:
        return False, "preceding observation unavailable at the decision time"
    if current.usable_at > current.event_time:
        return False, "decision observation unavailable at its own event time"
    if target.event_time <= current.event_time:
        return False, "target event is not strictly after decision event"
    return True, "causal availability check passed"


def run_battery(
    observations: Iterable[H10Observation],
    *,
    config: dict[str, object],
) -> list[BatteryResult]:
    """Run the predeclared battery while explicitly blocking invalid PIT cells."""
    hypotheses = config["hypotheses"]
    costs = [Decimal(str(x)) for x in config["one_way_cost_bps_grid"]]
    out: list[BatteryResult] = []

    by_instrument: dict[str, list[H10Observation]] = {}
    for obs in observations:
        by_instrument.setdefault(obs.instrument, []).append(obs)
    for values in by_instrument.values():
        values.sort(key=lambda x: (x.event_time, x.usable_at, x.observation_id))

    for hypothesis in hypotheses:
        hid = str(hypothesis["hypothesis_id"])
        rule = str(hypothesis["rule"])
        horizons = [int(x) for x in hypothesis["horizons"]]
        instruments = [str(x) for x in hypothesis["instruments"]]
        for instrument in instruments:
            series = by_instrument.get(instrument, [])
            for horizon in horizons:
                causal, reason = _causal_ready(series, horizon)
                for cost in costs:
                    for split in config["required_splits"]:
                        cell = BatteryCell(hid, rule, instrument, horizon, cost, str(split))
                        if not causal:
                            out.append(BatteryResult(cell, "blocked", reason, None, None, None))
                            continue

                        bounds = _split_bounds(
                            series,
                            Decimal(str(hypothesis["development_fraction"])),
                            Decimal(str(hypothesis["validation_fraction"])),
                            Decimal(str(hypothesis["holdout_fraction"])),
                        )
                        if not bounds:
                            out.append(BatteryResult(cell, "blocked", "invalid chronological split", None, None, None))
                            continue
                        lo, hi = bounds[split]
                        subset = series[lo:hi]
                        if len(subset) < horizon + 2:
                            out.append(BatteryResult(cell, "inconclusive", "split too small for horizon", None, None, None))
                            continue
                        trades = run_reference_backtest(
                            subset,
                            instrument=instrument,
                            rule=rule,  # type: ignore[arg-type]
                            horizon=horizon,
                            one_way_cost_bps=cost,
                        )
                        summary = summarize_reference_trades(trades)
                        start = subset[0].event_time.isoformat()
                        end = subset[-1].event_time.isoformat()
                        out.append(BatteryResult(cell, "completed", "executed", start, end, summary))
    return out


def write_results(results: Iterable[BatteryResult], path: str | Path) -> None:
    """Write deterministic JSONL evidence without silently upgrading blocked cells."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for row in results:
            payload = {
                "hypothesis_id": row.cell.hypothesis_id,
                "rule": row.cell.rule,
                "instrument": row.cell.instrument,
                "horizon": row.cell.horizon,
                "one_way_cost_bps": str(row.cell.one_way_cost_bps),
                "split": row.cell.split,
                "status": row.status,
                "reason": row.reason,
                "sample_start": row.sample_start,
                "sample_end": row.sample_end,
                "summary": row.summary,
            }
            handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")
