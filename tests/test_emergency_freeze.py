from pathlib import Path

import pytest

from apps.trading_runtime.node import RuntimeConfig, TradingNode
from packages.event_bus import EventBus


class Controller:
    strategy_id = "test"
    symbols = ("EURUSD",)

    def evaluate(self, **kwargs):
        raise AssertionError("strategy evaluation must not run while emergency freeze is asserted")


class Feed:
    def quote(self, symbol, *, now_ms):
        raise AssertionError("market data must not be touched while emergency freeze is asserted")

    def completed_bars(self, *, symbol, timeframe, count):
        return []

    def instrument_spec(self, symbol):
        raise AssertionError("broker spec must not be touched while emergency freeze is asserted")


def test_emergency_freeze_file_blocks_cycle(tmp_path: Path):
    freeze = tmp_path / "EMERGENCY_FREEZE"
    freeze.write_text("operator stop", encoding="utf-8")
    node = TradingNode(
        config=RuntimeConfig(allow_execution=False, emergency_freeze_path=str(freeze)),
        market_data=Feed(),
        controllers=(Controller(),),
        context_factory=lambda **kwargs: None,
        event_bus=EventBus(),
    )
    node.start()
    with pytest.raises(RuntimeError, match="EMERGENCY_FREEZE_FILE"):
        node.cycle()
    assert node.state.value == "FROZEN"
