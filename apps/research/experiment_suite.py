"""Fixed-design baseline experiment suite with chronological holdout discipline."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from .h10_ingest import H10Observation
from .reference_backtest import run_reference_backtest, summarize_reference_trades


@dataclass(frozen=True)
class Split:
    name: str
    start: object
    end: object


def chronological_splits(observations: Iterable[H10Observation]) -> list[Split]:
    dates = sorted({x.event_time.date() for x in observations})
    if len(dates) < 3:
        raise ValueError("at least three distinct dates are required")
    n = len(dates)
    a = max(1, n // 2)
    b = max(a + 1, (3 * n) // 4)
    b = min(b, n - 1)
    return [
        Split("development", dates[0], dates[a - 1]),
        Split("validation", dates[a], dates[b - 1]),
        Split("holdout", dates[b], dates[-1]),
    ]


def subset(observations: Iterable[H10Observation], split: Split) -> list[H10Observation]:
    return [x for x in observations if split.start <= x.event_time.date() <= split.end]


def run_fixed_grid(
    observations: Iterable[H10Observation],
    *,
    instrument: str,
    costs_bps: Iterable[Decimal] = (Decimal("0"), Decimal("1"), Decimal("2"), Decimal("5")),
    horizon: int = 1,
) -> list[dict[str, object]]:
    rows = list(observations)
    splits = chronological_splits(rows)
    results: list[dict[str, object]] = []
    for split in splits:
        sample = subset(rows, split)
        for rule in ("momentum", "reversal"):
            for cost in costs_bps:
                trades = run_reference_backtest(
                    sample,
                    instrument=instrument,
                    rule=rule,
                    horizon=horizon,
                    one_way_cost_bps=cost,
                )
                summary = summarize_reference_trades(trades)
                results.append(
                    {
                        "split": split.name,
                        "start": split.start.isoformat(),
                        "end": split.end.isoformat(),
                        "instrument": instrument,
                        "rule": rule,
                        "horizon": horizon,
                        "one_way_cost_bps": str(cost),
                        **{k: (str(v) if isinstance(v, Decimal) else v) for k, v in summary.items()},
                    }
                )
    return results
