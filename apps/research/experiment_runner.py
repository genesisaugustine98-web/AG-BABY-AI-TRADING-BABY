"""Fixed-design research runner for daily reference FX experiments."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from .h10_ingest import H10Observation
from .reference_backtest import run_reference_backtest, summarize_reference_trades


@dataclass(frozen=True)
class ResearchSplit:
    development_end: date
    validation_end: date

    def label(self, event_date: date) -> str:
        if event_date <= self.development_end:
            return "development"
        if event_date <= self.validation_end:
            return "validation"
        return "holdout"


def _split(observations: Iterable[H10Observation], split: ResearchSplit) -> dict[str, list[H10Observation]]:
    output = {"development": [], "validation": [], "holdout": []}
    for item in observations:
        output[split.label(item.event_time.date())].append(item)
    return output


def run_fixed_grid(
    observations: Iterable[H10Observation],
    *,
    instruments: Iterable[str],
    split: ResearchSplit,
    horizons: tuple[int, ...] = (1, 5),
    costs_bps: tuple[Decimal, ...] = (Decimal("0"), Decimal("2"), Decimal("5"), Decimal("10")),
) -> list[dict[str, object]]:
    """Run a predeclared grid without selecting parameters from outcomes."""
    source = list(observations)
    groups = _split(source, split)
    rows: list[dict[str, object]] = []
    for sample_name, sample in groups.items():
        for instrument in sorted(set(instruments)):
            for rule in ("momentum", "reversal"):
                for horizon in horizons:
                    for cost in costs_bps:
                        trades = run_reference_backtest(
                            sample,
                            instrument=instrument,
                            rule=rule,
                            horizon=horizon,
                            one_way_cost_bps=cost,
                        )
                        summary = summarize_reference_trades(trades)
                        rows.append({
                            "sample": sample_name,
                            "instrument": instrument,
                            "rule": rule,
                            "horizon": horizon,
                            "one_way_cost_bps": str(cost),
                            "n": summary["n"],
                            "mean_gross": None if summary["mean_gross"] is None else str(summary["mean_gross"]),
                            "mean_net": None if summary["mean_net"] is None else str(summary["mean_net"]),
                            "win_rate_net": None if summary["win_rate_net"] is None else str(summary["win_rate_net"]),
                            "sum_net": None if summary["sum_net"] is None else str(summary["sum_net"]),
                        })
    return rows
