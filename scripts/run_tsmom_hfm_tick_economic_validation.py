"""Read-only HFM tick-level execution-economic validation for fixed TSMOM.

Historical Bid/Ask quotes are taken from MT5 COPY_TICKS_INFO. Slippage, commission
and financing are explicit assumptions because hypothetical trades do not have real
broker deal records. No orders are submitted and no model is promoted.
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
from apps.execution_gateway.mt5_quote_history import MT5QuoteHistoryAdapter, RollingDailyQuoteCache
from packages.tsmom_economic import chronological_split_indices
from packages.tsmom_execution_economic import evaluate_split_with_quotes
from packages.tsmom_forecast import TSMOMForecastModel, dataset_fingerprint


def _iso(ms: int | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="USDJPY")
    parser.add_argument("--timeframe", default="H1")
    parser.add_argument("--count", type=int, default=5000)
    parser.add_argument("--lookback", type=int, default=24)
    parser.add_argument("--horizon", type=int, default=6)
    parser.add_argument("--delay-bars", type=int, default=1)
    parser.add_argument("--max-quote-staleness-seconds", type=int, default=300)
    parser.add_argument("--slippage-bps-one-way", type=Decimal, default=Decimal("0"))
    parser.add_argument("--commission-bps-one-way", type=Decimal, default=Decimal("0"))
    parser.add_argument("--financing-bps-per-day", type=Decimal, default=Decimal("0"))
    parser.add_argument("--output", default="artifacts/tsmom_usdjpy_h1_tick_economic.json")
    parser.add_argument("--code-commit-sha", default=os.getenv("GIT_COMMIT_SHA", "unknown"))
    args = parser.parse_args()

    timeframe = args.timeframe.upper().strip()
    intervals = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}
    if timeframe not in intervals:
        raise SystemExit(f"unsupported timeframe:{timeframe}")
    if args.max_quote_staleness_seconds < 0:
        raise SystemExit("max quote staleness cannot be negative")

    gateway = DemoOnlyMT5Gateway()
    gateway.connect_and_verify_demo()
    try:
        api = gateway.mt5_api()
        rows = MT5MarketDataAdapter(api).fetch_completed_bars(
            symbol=args.symbol, timeframe=timeframe, count=args.count
        )
        fingerprint = dataset_fingerprint(rows)
        model = TSMOMForecastModel(
            lookback_bars=args.lookback,
            horizon_bars=args.horizon,
            min_training_samples=30,
            bar_interval_seconds=intervals[timeframe],
        )
        validation = model.fit(
            rows, dataset_fingerprint=fingerprint, code_commit_sha=args.code_commit_sha
        )
        splits = chronological_split_indices(len(rows))

        quote_adapter = MT5QuoteHistoryAdapter(api)
        quote_cache = RollingDailyQuoteCache(quote_adapter, max_days=2)

        def provider(timestamp_ms: int):
            return quote_cache.quote_at_or_before(
                symbol=args.symbol,
                event_time_ms=timestamp_ms,
                max_gap_ms=args.max_quote_staleness_seconds * 1000,
            )

        results = {}
        for split_name in ("validation", "holdout"):
            lo, hi = splits[split_name]
            result = evaluate_split_with_quotes(
                model,
                rows,
                split=split_name,
                start_index=lo,
                end_index=hi,
                quote_provider=provider,
                max_quote_gap_ms=args.max_quote_staleness_seconds * 1000,
                slippage_one_way_bps=args.slippage_bps_one_way,
                commission_one_way_bps=args.commission_bps_one_way,
                financing_bps_per_day=args.financing_bps_per_day,
                delay_bars=args.delay_bars,
            )
            results[split_name] = {
                "n": result.n,
                "skipped_no_signal": result.skipped_no_signal,
                "missing_entry_quote": result.missing_entry_quote,
                "missing_exit_quote": result.missing_exit_quote,
                "sample_start": _iso(result.sample_start),
                "sample_end": _iso(result.sample_end),
                "max_quote_staleness_seconds": args.max_quote_staleness_seconds,
                "slippage_one_way_bps": str(result.slippage_one_way_bps),
                "commission_one_way_bps": str(result.commission_one_way_bps),
                "financing_bps_per_day": str(result.financing_bps_per_day),
                "mean_gross": None if result.mean_gross is None else str(result.mean_gross),
                "mean_net": None if result.mean_net is None else str(result.mean_net),
                "cumulative_net": None if result.cumulative_net is None else str(result.cumulative_net),
                "max_drawdown": None if result.max_drawdown is None else str(result.max_drawdown),
                "win_rate_net": None if result.win_rate_net is None else str(result.win_rate_net),
                "profit_factor": None if result.profit_factor is None else str(result.profit_factor),
                "sharpe_like": None if result.sharpe_like is None else str(result.sharpe_like),
                "mean_entry_spread_bps": None if result.mean_entry_spread_bps is None else str(result.mean_entry_spread_bps),
                "median_entry_spread_bps": None if result.median_entry_spread_bps is None else str(result.median_entry_spread_bps),
                "mean_exit_spread_bps": None if result.mean_exit_spread_bps is None else str(result.mean_exit_spread_bps),
                "mean_midpoint_gross": None if result.mean_midpoint_gross is None else str(result.mean_midpoint_gross),
                "mean_spread_drag_bps": None if result.mean_spread_drag_bps is None else str(result.mean_spread_drag_bps),
                "median_exit_spread_bps": None if result.median_exit_spread_bps is None else str(result.median_exit_spread_bps),
            }

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
            "execution_price_method": {
                "entry": "BUY=ask, SELL=bid",
                "exit": "BUY=bid, SELL=ask",
                "historical_quote_source": "MT5 COPY_TICKS_INFO",
                "quote_selection": "latest valid Bid/Ask quote at or before scheduled execution timestamp",
                "max_quote_staleness_seconds": args.max_quote_staleness_seconds,
            },
            "cost_assumptions": {
                "slippage_one_way_bps": str(args.slippage_bps_one_way),
                "commission_one_way_bps": str(args.commission_bps_one_way),
                "financing_bps_per_day": str(args.financing_bps_per_day),
                "note": "Commission and financing are assumptions for hypothetical trades; they are not inferred from unrelated broker deal records.",
            },
            "split_policy": {
                "development": "60%",
                "validation": "20%",
                "holdout": "20%",
                "fit_uses_development_only": True,
                "holdout_used_for_selection": False,
            },
            "results": results,
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
