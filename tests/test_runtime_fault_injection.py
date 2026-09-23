from decimal import Decimal
import pytest

from apps.trading_runtime.node import RuntimeConfig, TradingNode
from packages.event_bus import EventBus
from packages.events import StrategyDecision
from packages.models import EventState, Forecast, InstrumentSpec, MarketState, Quote
from packages.opportunity import OpportunityCandidate


class Clock:
    def now_ms(self):
        return 1000


class BadFeed:
    def quote(self, symbol, *, now_ms):
        return Quote(symbol, Decimal("1.1"), Decimal("1.0"), now_ms, "test")

    def completed_bars(self, *, symbol, timeframe, count):
        return []

    def instrument_spec(self, symbol):
        return InstrumentSpec(
            symbol, "EUR", "USD", Decimal("100000"), Decimal("0.00001"),
            Decimal("0.00001"), Decimal("1"), Decimal("0.01"), Decimal("100"), Decimal("0.01")
        )


class Controller:
    strategy_id = "s1"
    symbols = ("EURUSD",)

    def evaluate(self, **kwargs):
        forecast = Forecast(
            "m", "1", 1000, 3600, Decimal("0.001"), "fraction",
            Decimal("0.7"), Decimal("0.8"), Decimal("0.8")
        )
        candidate = OpportunityCandidate(
            "c1", "EURUSD", "BUY",
            Decimal("0.001"), Decimal("0.7"), Decimal("0.8"),
            Decimal("0.0001"), Decimal("0.0001"), Decimal("0.0008"), Decimal("0.001"),
            "ADMITTED", "m", "1", (), "executable", "s1"
        )
        return StrategyDecision("s1", "EURUSD", forecast, candidate)


def fail_market(**kwargs):
    raise RuntimeError("MARKET_STATE_FAILURE")


def test_market_fault_freezes_node():
    node = TradingNode(
        config=RuntimeConfig(allow_execution=False),
        market_data=BadFeed(),
        controllers=(Controller(),),
        context_factory=lambda **kwargs: None,
        market_state_factory=fail_market,
        clock=Clock(),
        event_bus=EventBus(),
    )
    node.start()
    with pytest.raises(RuntimeError, match="MARKET_STATE_FAILURE"):
        node.cycle()
    assert node.state.value == "FROZEN"
