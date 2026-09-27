"""Read-only HFM economic validation for the fixed TSMOM model.

Fits only on development data, evaluates a frozen model on validation and untouched
holdout data, and reports sensitivity to explicit assumed one-way transaction costs.
No broker order functions are called and no model registry writes are performed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.execution_gateway.mt5_gateway import DemoOnlyMT5Gateway
from apps.execution_gateway.mt5_market_data import MT5MarketDataAdapter
from packages.tsmom_economic import chronological_split_indices, evaluate_split_sensitivity
from packages.tsmom_forecast import TSMOMForecastModel, dataset_fingerprint


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="USDJPY")
    parser.add_argument("--timeframe", default="H1")
    parser.add_argument("--count", type=int, default=20000)
    parser.add_argument("--lookback", type=int, default=24)
    parser.add_argument("--horizon", type=int, default=6)
    parser.add_argument("--delay-bars", type=int, default=1)
    parser.add_argument("--costs-bps", default="0,1,2,5,10")
    parser.add_argument("--output", default="artifacts/tsmom_usdjpy_h1_economic.json")
    parser.add_argument("--code-commit-sha", default=os.getenv("GIT_COMMIT_SHA", "unknown"))
    args = parser.parse_args()

    timeframe = args.timeframe.upper().strip()
    intervals = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}
    if timeframe not in intervals:
        raise SystemExit(f"unsupported timeframe:{timeframe}")

    costs = tuple(Decimal(x.strip()) for x in args.costs_bps.split(",") if x.strip())
    gateway = DemoOnlyMT5Gateway()
    gateway.connect_and_verify_demo()
    try:
        rows = MT5MarketDataAdapter(gateway.mt5_api()).fetch_completed_bars(
            symbol=args.symbol,
            timeframe=timeframe,
            count=args.count,
        )
        fingerprint = dataset_fingerprint(rows)
        model = TSMOMForecastModel(
            lookback_bars=args.lookback,
            horizon_bars=args.horizon,
            min_training_samples=30,
            bar_interval_seconds=intervals[timeframe],
        )
        validation = model.fit(
            rows,
            dataset_fingerprint=fingerprint,
            code_commit_sha=args.code_commit_sha,
        )
        splits = chronological_split_indices(len(rows))

        split_results = {}
        for split_name in ("validation", "holdout"):
            lo, hi = splits[split_name]
            split_results[split_name] = evaluate_split_sensitivity(
                model,
                rows,
                split=split_name,
                start_index=lo,
                end_index=hi,
                one_way_costs_bps=costs,
                delay_bars=args.delay_bars,
            )

        sensitivity = []
        for cost in costs:
            cells = {}
            for split_name in ("validation", "holdout"):
                result = split_results[split_name][cost]
                cells[split_name] = {
                    "n": result.n,
                    "skipped_no_signal": result.skipped_no_signal,
                    "sample_start": _iso(result.sample_start) if result.sample_start else None,
                    "sample_end": _iso(result.sample_end) if result.sample_end else None,
                    "assumed_one_way_cost_bps": str(result.assumed_one_way_cost_bps),
                    "delay_bars": result.delay_bars,
                    "horizon_bars": result.horizon_bars,
                    "mean_gross": None if result.mean_gross is None else str(result.mean_gross),
                    "mean_net": None if result.mean_net is None else str(result.mean_net),
                    "cumulative_net": None if result.cumulative_net is None else str(result.cumulative_net),
                    "max_drawdown": None if result.max_drawdown is None else str(result.max_drawdown),
                    "win_rate_net": None if result.win_rate_net is None else str(result.win_rate_net),
                    "profit_factor": None if result.profit_factor is None else str(result.profit_factor),
                    "sharpe_like": None if result.sharpe_like is None else str(result.sharpe_like),
                    "breakeven_one_way_cost_bps": None if result.breakeven_one_way_cost_bps is None else str(result.breakeven_one_way_cost_bps),
                }
            sensitivity.append(cells)

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "environment": "demo",
            "broker": "HFM_MT5",
            "symbol": args.symbol,
            "timeframe": timeframe,
            "bar_count": len(rows),
            "sample_start": _iso(rows[0].event_time_ms),
            "sample_end": _iso(rows[-1].event_time_ms),
            "dataset_fingerprint": fingerprint,
            "model": {
                "model_id": validation.model_id,
                "version": validation.version,
                "lookback_bars": validation.lookback_bars,
                "horizon_bars": validation.horizon_bars,
                "development_n": validation.development_n,
                "validation_n": validation.validation_n,
                "holdout_n": validation.holdout_n,
                "validation_ece": str(validation.validation_ece),
                "calibration_score": str(validation.calibration_score),
                "calibration_gate": validation.calibration_gate,
                "validation_status": validation.validation_status,
                "feature_fingerprint": validation.feature_fingerprint,
                "code_commit_sha": validation.code_commit_sha,
            },
            "split_policy": {
                "development": "60%",
                "validation": "20%",
                "holdout": "20%",
                "fit_uses_development_only": True,
                "holdout_used_for_selection": False,
            },
            "economic_sensitivity": sensitivity,
            "research_conclusion": "DESCRIPTIVE_ONLY_NOT_PROMOTED",
            "execution_authorization": "NONE",
        }
        rendered = json.dumps(report, indent=2, sort_keys=True)
        print(rendered)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
        return 0
    finally:
        gateway.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
