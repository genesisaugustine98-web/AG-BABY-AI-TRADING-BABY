"""Continuous free/public market-observation daemon.

This process is intentionally incapable of broker execution. It writes observation
snapshots locally and exposes a local-only health endpoint for supervision.
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

from .free_stack_sources import BinancePublicClient, KrakenFuturesPublicClient


@dataclass
class Health:
    started_at_ms: int
    last_success_at_ms: int = 0
    last_error: str | None = None
    observations: int = 0
    failures: int = 0
    running: bool = True


class HealthHandler(BaseHTTPRequestHandler):
    server_version = "AG-BABY-free-stack/1.0"

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
                f"ag_baby_observation_failures_total {health.failures}\n"
                f"ag_baby_last_success_timestamp_ms {health.last_success_at_ms}\n"
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
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AG-BABY free/public observation daemon")
    parser.add_argument("--interval-seconds", type=int, default=int(os.getenv("OBSERVATION_INTERVAL_SECONDS", "60")))
    parser.add_argument("--output-dir", default=os.getenv("OBSERVATION_OUTPUT_DIR", "data/live_observations"))
    parser.add_argument("--bind", default=os.getenv("OBSERVATION_HEALTH_BIND", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("OBSERVATION_HEALTH_PORT", "8787")))
    parser.add_argument("--binance-symbol", default=os.getenv("BINANCE_SYMBOL", "BTCUSDT"))
    parser.add_argument("--kraken-symbol", default=os.getenv("KRAKEN_FUTURES_SYMBOL", "PI_XBTUSD"))
    args = parser.parse_args(argv)

    if args.interval_seconds < 15:
        raise SystemExit("interval must be >= 15 seconds to avoid unnecessary provider pressure")
    if not 1 <= args.port <= 65535:
        raise SystemExit("invalid port")

    root = Path(args.output_dir)
    health = Health(started_at_ms=int(time.time() * 1000))
    server = ThreadingHTTPServer((args.bind, args.port), HealthHandler)
    server.health = health  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    stop = threading.Event()

    def _stop(_signum: int, _frame: object) -> None:
        stop.set()
        health.running = False

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    while not stop.wait(args.interval_seconds):
        cycle_started = int(time.time() * 1000)
        try:
            b = BinancePublicClient().ticker(args.binance_symbol)
            k = KrakenFuturesPublicClient().analytics(args.kraken_symbol, "funding", interval=3600)
            _write_snapshot(
                root,
                {
                    "schema_version": "1",
                    "observed_at_ms": cycle_started,
                    "binance": {"url": b.url, "sha256": b.sha256, "payload": b.payload},
                    "kraken_futures": {"url": k.url, "sha256": k.sha256, "payload": k.payload},
                },
            )
            health.last_success_at_ms = cycle_started
            health.last_error = None
            health.observations += 1
            health.failures = 0
        except Exception as exc:  # fail closed for data consumers; daemon stays supervised
            health.last_error = type(exc).__name__
            health.failures += 1

    server.shutdown()
    server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
