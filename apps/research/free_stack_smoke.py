"""Smoke-test public free data endpoints without broker credentials."""
from __future__ import annotations

import argparse
import json
import sys

from .free_stack_sources import BinancePublicClient, KrakenFuturesPublicClient


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AG-BABY free data stack smoke test")
    parser.add_argument("--binance-symbol", default="BTCUSDT")
    parser.add_argument("--kraken-symbol", default="PI_XBTUSD")
    args = parser.parse_args(argv)

    results: list[dict[str, object]] = []
    failures = 0
    try:
        snap = BinancePublicClient().ticker(args.binance_symbol)
        results.append({"source": "binance", "sha256": snap.sha256, "ok": True})
    except Exception as exc:
        failures += 1
        results.append({"source": "binance", "ok": False, "error": type(exc).__name__})
    try:
        snap = KrakenFuturesPublicClient().analytics(args.kraken_symbol, "funding", interval=3600)
        results.append({"source": "kraken_futures", "sha256": snap.sha256, "ok": True})
    except Exception as exc:
        failures += 1
        results.append({"source": "kraken_futures", "ok": False, "error": type(exc).__name__})

    print(json.dumps({"ok": failures == 0, "results": results}, sort_keys=True))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
