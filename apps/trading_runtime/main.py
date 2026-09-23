"""Process entrypoint for the canonical trading runtime."""
from __future__ import annotations

import argparse
import logging
import signal
import sys

from .canonical import CanonicalConfig, CanonicalTradingSystem


LOG = logging.getLogger("ag-trading-runtime")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AG-BABY canonical demo trading runtime")
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=None,
        help="stop cleanly after N cycles; omit for continuous operation",
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="validate environment configuration without connecting to MT5",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = build_parser().parse_args(argv)
    try:
        config = CanonicalConfig.from_env()
    except Exception as exc:
        LOG.error("configuration rejected: %s", exc)
        return 2

    if args.check_config:
        LOG.info(
            "configuration valid: environment=%s execution=%s symbols=%s",
            config.environment,
            config.allow_execution,
            ",".join(config.symbols),
        )
        return 0

    system: CanonicalTradingSystem | None = None

    def shutdown(_signum, _frame) -> None:
        nonlocal system
        if system is not None:
            LOG.warning("shutdown signal received; freezing and stopping runtime")
            try:
                system.stop()
            except Exception:
                LOG.exception("runtime stop failed")

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        system = CanonicalTradingSystem.create(config)
        LOG.info(
            "canonical runtime created: node=%s environment=%s execution=%s symbols=%s",
            config.node_id,
            config.environment,
            config.allow_execution,
            ",".join(config.symbols),
        )
        system.run(max_cycles=args.max_cycles)
        return 0
    except KeyboardInterrupt:
        if system is not None:
            system.stop()
        return 0
    except Exception:
        LOG.exception("canonical runtime terminated in fail-safe state")
        return 1


if __name__ == "__main__":
    sys.exit(main())
