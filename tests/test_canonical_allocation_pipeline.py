from decimal import Decimal

from apps.trading_runtime.node import RuntimeConfig, TradingNode
from packages.event_bus import EventBus
from packages.events import StrategyDecision
from packages.models import AdmissionContext, EventState, Forecast, InstrumentSpec, MarketState, Quote, TradeIntent
from packages.opportunity import OpportunityCandidate
from packages.portfolio_risk import PortfolioRiskDecision
from packages.strategy_allocator import AllocationLimits, StrategyAllocator


class Clock:
    def now_ms(self):
        return 1_000_000


class Feed:
    def quote(self, symbol, *, now_ms):
        return Quote(symbol, Decimal("1"), Decimal("1.0001"), now_ms - 100, "test")

    def completed_bars(self, *, symbol, timeframe, count):
        return []

    def instrument_spec(self, symbol):
        return InstrumentSpec(
            symbol, "EUR", "USD", Decimal("100000"), Decimal("0.00001"),
            Decimal("0.00001"), Decimal("1"), Decimal("0.01"), Decimal("100"), Decimal("0.01")
        )


class Controller:
    strategy_id = "tsmom"
    symbols = ("EURUSD",)

    def evaluate(self, **kwargs):
        forecast = Forecast(
            "tsmom-fixed-v1", "1", 999_900, 3600, Decimal("0.002"), "fraction",
            Decimal("0.70"), Decimal("0.80"), Decimal("0.80"),
        )
        candidate = OpportunityCandidate(
            "opp-1", "EURUSD", "BUY", Decimal("0.002"), Decimal("0.70"),
            Decimal("0.80"), Decimal("0.0001"), Decimal("0.0001"), Decimal("0.0018"),
            Decimal("0.006"), "ADMITTED", "tsmom-fixed-v1", "1", (), "executable", "tsmom"
        )
        return StrategyDecision("tsmom", "EURUSD", forecast, candidate)


class Execution:
    def __init__(self):
        self.calls = []

    def submit(self, **kwargs):
        self.calls.append(kwargs)
        raise AssertionError("allocation rejection must occur before execution")


def test_allocator_is_before_execution_and_rejected_candidate_never_builds_order():
    execution = Execution()
    context_calls = []

    def context_factory(**kwargs):
        context_calls.append(kwargs)
        raise AssertionError("context construction must occur after allocation")

    node = TradingNode(
        config=RuntimeConfig(allow_execution=True),
        market_data=Feed(),
        controllers=(Controller(),),
        context_factory=context_factory,
        execution=execution,
        market_state_factory=lambda *, quote, now_ms: MarketState(
            EventState.NORMAL, 100, Decimal("0.0001"), Decimal("0.9"),
            Decimal("0.1"), Decimal("0.95"), Decimal("0.99")
        ),
        allocator=StrategyAllocator(
            AllocationLimits(
                max_total_risk=Decimal("0.005"),
                max_per_strategy_risk=Decimal("0.005"),
                max_per_instrument_risk=Decimal("0.005"),
                max_candidates=8,
            )
        ),
        strategy_order=("tsmom",),
        event_bus=EventBus(),
        clock=Clock(),
    )
    node.start()
    node.cycle()

    assert not execution.calls
    assert not context_calls
    allocation_events = [e for e in node.events.history() if type(e).__name__ == "AllocationDecisionEvent"]
    assert allocation_events and allocation_events[0].approved is False


class AllowingContext:
    def __call__(self, **kwargs):
        return (
            TradeIntent(
                "intent-1", "tsmom", "1", "policy", "EURUSD", "BUY",
                Decimal("0.01"), "MARKET", None, Decimal("0.999"), Decimal("1.01"),
                1_000_000, 1_003_600, Decimal("0.001"), Decimal("0.005"), 3600,
            ),
            kwargs["decision"],
        )


def test_exact_portfolio_gate_runs_after_sizing_and_before_execution():
    execution = Execution()
    node = TradingNode(
        config=RuntimeConfig(allow_execution=True),
        market_data=Feed(),
        controllers=(Controller(),),
        context_factory=AllowingContext(),
        execution=execution,
        market_state_factory=lambda *, quote, now_ms: MarketState(
            EventState.NORMAL, 100, Decimal("0.0001"), Decimal("0.9"),
            Decimal("0.1"), Decimal("0.95"), Decimal("0.99")
        ),
        allocator=StrategyAllocator(
            AllocationLimits(
                max_total_risk=Decimal("0.01"),
                max_per_strategy_risk=Decimal("0.01"),
                max_per_instrument_risk=Decimal("0.01"),
                max_candidates=8,
            )
        ),
        portfolio_risk_gate=lambda **kwargs: PortfolioRiskDecision(
            False, ("PORTFOLIO_TEST_DENY",), Decimal("0.02"), Decimal("0.01"),
            Decimal("0.01"), Decimal("0.10"), Decimal("0.01"),
        ),
        strategy_order=("tsmom",),
        event_bus=EventBus(),
        clock=Clock(),
    )
    node.start()
    node.cycle()
    assert not execution.calls
    events = [e for e in node.events.history() if type(e).__name__ == "PortfolioRiskDecisionEvent"]
    assert events and events[0].approved is False
    assert events[0].reasons == ("PORTFOLIO_TEST_DENY",)


def test_execution_guard_is_last_moment_fail_closed_boundary():
    execution = Execution()
    context = AllowingContext()

    def guard():
        raise RuntimeError("LEASE_LOST")

    node = TradingNode(
        config=RuntimeConfig(allow_execution=True),
        market_data=Feed(),
        controllers=(Controller(),),
        context_factory=context,
        execution=execution,
        market_state_factory=lambda *, quote, now_ms: MarketState(
            EventState.NORMAL, 100, Decimal("0.0001"), Decimal("0.9"),
            Decimal("0.1"), Decimal("0.95"), Decimal("0.99")
        ),
        allocator=StrategyAllocator(
            AllocationLimits(
                max_total_risk=Decimal("0.01"),
                max_per_strategy_risk=Decimal("0.01"),
                max_per_instrument_risk=Decimal("0.01"),
                max_candidates=8,
            )
        ),
        execution_guard=guard,
        strategy_order=("tsmom",),
        event_bus=EventBus(),
        clock=Clock(),
    )
    node.start()
    try:
        node.cycle()
    except RuntimeError as exc:
        assert str(exc) == "LEASE_LOST"
    else:
        raise AssertionError("execution guard must stop submission")
    assert not execution.calls
    assert node.state.value == "FROZEN"
