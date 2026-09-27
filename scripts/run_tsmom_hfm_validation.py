"""Read-only HFM demo validation runner for the fixed-design TSMOM model.

This script connects only to the already-approved HFM DEMO terminal, downloads completed
bars, computes a dataset fingerprint, fits the calibration layer, and emits a JSON report.
It never calls order_check/order_send and never writes model_registry automatically.
"""
from __future__ import annotations

import argparse
import sys
import json
import os
from datetime import datetime, timezone
from pathlib import Path

# When invoked as `python scripts/<file>.py`, Python places `scripts/` on
# sys.path rather than the repository root. Add the root explicitly so the
# repository packages resolve exactly as they do under pytest/CI.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.execution_gateway.mt5_gateway import DemoOnlyMT5Gateway
from apps.execution_gateway.mt5_market_data import MT5MarketDataAdapter
from packages.tsmom_forecast import TSMOMForecastModel, dataset_fingerprint


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="USDJPY")
    parser.add_argument("--timeframe", default="H1")
    parser.add_argument("--count", type=int, default=5000)
    parser.add_argument("--lookback", type=int, default=24)
    parser.add_argument("--horizon", type=int, default=6)
    parser.add_argument("--output", default="")
    parser.add_argument("--code-commit-sha", default=os.getenv("GIT_COMMIT_SHA", "unknown"))
    args = parser.parse_args()

    gateway = DemoOnlyMT5Gateway()
    gateway.connect_and_verify_demo()
    try:
        adapter = MT5MarketDataAdapter(gateway.mt5_api())
        interval_seconds = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}[args.timeframe.upper()]
        rows = adapter.fetch_completed_bars(
            symbol=args.symbol,
            timeframe=args.timeframe,
            count=args.count,
        )
        fingerprint = dataset_fingerprint(rows)
        model = TSMOMForecastModel(
            lookback_bars=args.lookback,
            horizon_bars=args.horizon,
            min_training_samples=30,
            bar_interval_seconds=interval_seconds,
        )
        validation = model.fit(
            rows,
            dataset_fingerprint=fingerprint,
            code_commit_sha=args.code_commit_sha,
        )
        decision_time_ms = rows[-1].event_time_ms
        forecast = model.predict(rows, decision_time_ms=decision_time_ms)

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "environment": "demo",
            "broker": "HFM_MT5",
            "symbol": args.symbol,
            "timeframe": args.timeframe.upper(),
            "bar_count": len(rows),
            "dataset_fingerprint": fingerprint,
            "validation": {
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
                "dataset_fingerprint": validation.dataset_fingerprint,
                "code_commit_sha": validation.code_commit_sha,
            },
            "latest_forecast": {
                "model_id": forecast.model_id,
                "version": forecast.version,
                "generated_at_ms": forecast.generated_at_ms,
                "horizon_seconds": forecast.horizon_seconds,
                "expected_return": str(forecast.expected_return),
                "probability_up": str(forecast.probability_up),
                "calibration_score": str(forecast.calibration_score),
                "confidence": str(forecast.confidence),
                "evidence_ids": list(forecast.evidence_ids),
            },
            "execution_authorization": "NONE",
        }
        rendered = json.dumps(report, indent=2, sort_keys=True)
        print(rendered)
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered + "\n", encoding="utf-8")
        return 0
    finally:
        gateway.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
