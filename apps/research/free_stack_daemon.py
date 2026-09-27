"""Continuous free/public research-fabric daemon.

This process is intentionally incapable of broker execution. It collects public
observations, runs the existing research engine on closed candles, persists compact
snapshots, and may publish source health to the Supabase control plane.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import threading
import time
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from packages.horizon import Timeframe

from integrations.supabase_source_health import SupabaseSourceHealthPublisher

from .free_stack_adapter import FreeStackResearchAdapter
from .free_stack_research_engine import FreeStackResearchEngine
from .free_stack_sources import BinancePublicClient, KrakenFuturesPublicClient


@dataclass
class Health:
    started_at_ms: int
    last_success_at_ms: int = 0
    last_research_at_ms: int = 0
    last_error: str | None = None
    observations: int = 0
    research_runs: int = 0
    failures: int = 0
    running: bool = True


class HealthHandler(BaseHTTPRequestHandler):
    server_version = "AG-BABY-free-stack/2.0"

    def do_GET(self) -> None:  # noqa: N802
        health: Health = self.server.health  # type: ignore[attr-defined]
        if self.path == "/healthz":
            payload = asdict(health)
            payload["healthy"] = health.running and health.last_success_at_ms > 0 and health.failures < 10
            body = json.dumps(payload, sort_keys=True).encode("utf-8")
            self.send_response(200 if payload["healthy"] else 503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/metrics":
            metrics = (
                f"ag_baby_observations_total {health.observations}\n"
                f"ag_baby_research_runs_total {health.research_runs}\n"
                f"ag_baby_observation_failures_total {health.failures}\n"
                f"ag_baby_last_success_timestamp_ms {health.last_success_at_ms}\n"
                f"ag_baby_last_research_timestamp_ms {health.last_research_at_ms}\n"
                f"ag_baby_process_running {1 if health.running else 0}\n"
            )
            body = metrics.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, _format: str, *_args: object) -> None:
        return


def _write_snapshot(root: Path, payload: dict[str, object]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d", time.gmtime())
    path = root / f"observations-{stamp}.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str) + "\n")


def _parse_horizons(raw: str) -> tuple[Timeframe, ...]:
    values = []
    for value in raw.split(","):
        value = value.strip().upper()
        if not value:
            continue
        values.append(Timeframe(value))
    if not values:
        raise ValueError("at least one research horizon is required")
    return tuple(dict.fromkeys(values))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AG-BABY free/public research-fabric daemon")
    parser.add_argument("--interval-seconds", type=int, default=int(os.getenv("OBSERVATION_INTERVAL_SECONDS", "60")))
    parser.add_argument("--research-interval-seconds", type=int, default=int(os.getenv("RESEARCH_INTERVAL_SECONDS", "900")))
    parser.add_argument("--output-dir", default=os.getenv("OBSERVATION_OUTPUT_DIR", "data/live_observations"))
    parser.add_argument("--bind", default=os.getenv("OBSERVATION_HEALTH_BIND", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("OBSERVATION_HEALTH_PORT", "8787")))
    parser.add_argument("--binance-symbol", default=os.getenv("BINANCE_SYMBOL", "BTCUSDT"))
    parser.add_argument("--kraken-symbol", default=os.getenv("KRAKEN_FUTURES_SYMBOL", "PI_XBTUSD"))
    parser.add_argument(
        "--research-horizons",
        default=os.getenv("RESEARCH_HORIZONS", "M15,H1,H4,D1"),
        help="comma-separated native Binance horizons",
    )
    args = parser.parse_args(argv)

    if args.interval_seconds < 15:
        raise SystemExit("interval must be >= 15 seconds to avoid unnecessary provider pressure")
    if args.research_interval_seconds < 300:
        raise SystemExit("research interval must be >= 300 seconds")
    if not 1 <= args.port <= 65535:
        raise SystemExit("invalid port")
    try:
        horizons = _parse_horizons(args.research_horizons)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    root = Path(args.output_dir)
    health = Health(started_at_ms=int(time.time() * 1000))
    server = ThreadingHTTPServer((args.bind, args.port), HealthHandler)
    server.health = health  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    binance = BinancePublicClient()
    kraken = KrakenFuturesPublicClient()
    adapter = FreeStackResearchAdapter(binance=binance, kraken=kraken)
    engine = FreeStackResearchEngine(client=binance)
    publisher = SupabaseSourceHealthPublisher()
    stop = threading.Event()
    next_research_at = 0.0

    def _stop(_signum: int, _frame: object) -> None:
        stop.set()
        health.running = False

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    while not stop.wait(args.interval_seconds):
        cycle_started = int(time.time() * 1000)
        try:
            results = adapter.collect(
                binance_symbol=args.binance_symbol,
                kraken_symbol=args.kraken_symbol,
            )
            payload: dict[str, object] = {
                "schema_version": "2",
                "observed_at_ms": cycle_started,
                "source_results": [
                    {
                        "source_id": result.source_id,
                        "instrument": result.instrument,
                        "status": result.status,
                        "reason": result.reason,
                        "snapshot_sha256": result.snapshot_sha256,
                        "observation": None if result.observation is None else {
                            "instrument": result.observation.instrument,
                            "event_time": result.observation.event_time.isoformat(),
                            "usable_at": result.observation.usable_at.isoformat(),
                            "close": str(result.observation.close),
                            "source": result.observation.source,
                            "source_version": result.observation.source_version,
                            "observation_id": result.observation.observation_id,
                        },
                    }
                    for result in results
                ],
            }

            for result in results:
                score = 1.0 if result.status == "ok" else 0.0
                try:
                    publisher.publish(
                        source_id=result.source_id,
                        health=score,
                        metadata={
                            "last_status": result.status,
                            "last_reason": result.reason,
                            "snapshot_sha256": result.snapshot_sha256,
                        },
                    )
                except Exception:
                    # The control plane observes source health when available, but a
                    # failed health write never becomes implicit trading permission.
                    pass

            now = time.monotonic()
            if now >= next_research_at:
                research = engine.analyze(
                    symbol=args.binance_symbol,
                    timeframes=horizons,
                    execution_latency_seconds=5,
                )
                payload["research"] = {
                    "symbol": research.symbol,
                    "proposal": {
                        "timeframe": research.proposal.timeframe.value,
                        "direction": research.proposal.direction,
                        "score": str(research.proposal.score),
                        "uncertainty": str(research.proposal.uncertainty),
                        "expected_hold_seconds": research.proposal.expected_hold_seconds,
                        "reason_codes": research.proposal.reason_codes,
                    },
                    "forecasts": [
                        {
                            "timeframe": result.timeframe.value,
                            "expected_return": str(result.forecast.expected_return),
                            "probability_up": str(result.forecast.probability_up),
                            "calibration_score": str(result.forecast.calibration_score),
                            "confidence": str(result.forecast.confidence),
                            "dataset_fingerprint": result.model.validation.dataset_fingerprint
                            if result.model.validation else None,
                        }
                        for result in research.forecasts
                    ],
                    "dataset_fingerprints": research.dataset_fingerprints,
                }
                health.last_research_at_ms = cycle_started
                health.research_runs += 1
                next_research_at = now + args.research_interval_seconds

            _write_snapshot(root, payload)
            health.last_success_at_ms = cycle_started
            health.last_error = None
            health.observations += 1
            health.failures = 0
        except Exception as exc:  # data consumers see degraded state; supervisor stays active
            health.last_error = type(exc).__name__
            health.failures += 1

    server.shutdown()
    server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
