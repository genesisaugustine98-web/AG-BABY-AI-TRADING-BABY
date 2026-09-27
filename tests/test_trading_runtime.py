from decimal import Decimal

from apps.trading_runtime.node import RuntimeConfig, TradingNode
from packages.event_bus import EventBus
from packages.models import AdmissionContext, EventState, Forecast, InstrumentSpec, MarketState, PortfolioState, Quote, TradeIntent
from packages.tsmom_forecast import PriceBar, TSMOMForecastModel
from packages.strategy_controller import TSMOMController


class Clock:
    def __init__(self):
        self.t = 700_000_000

    def now_ms(self):
        return self.t


class Feed:
    def __init__(self):
        self.instrument = InstrumentSpec(
            "EURUSD",
            "EUR",
            "USD",
            Decimal("100000"),
            Decimal("0.00001"),
            Decimal("0.00001"),
            Decimal("1"),
            Decimal("0.01"),
            Decimal("100"),
            Decimal("0.01"),
        )

    def quote(self, symbol, *, now_ms):
        return Quote(symbol, Decimal("1.10000"), Decimal("1.10001"), now_ms - 100, "test")

    def completed_bars(self, *, symbol, timeframe, count):
        out = []
        close = Decimal("1")
        for i in range(180):
            close += Decimal("0.0005") if i % 3 else Decimal("0.0002")
            t = 1_000_000 + i * 3_600_000
            out.append(PriceBar(symbol, t, t + 3_600_000, close, "test", "1", f"{symbol}-{i}"))
        return out

    def instrument_spec(self, symbol):
        return self.instrument


def model():
    bars = Feed().completed_bars(symbol="EURUSD", timeframe="H1", count=180)
    m = TSMOMForecastModel(
        lookback_bars=8,
        horizon_bars=3,
        min_training_samples=20,
        bar_interval_seconds=3600,
    )
    m.fit(bars, dataset_fingerprint="d", code_commit_sha="c")
    return m


class Controller(TSMOMController):
    pass


def market_state(*, quote, now_ms):
    return MarketState(
        EventState.NORMAL,
        now_ms - quote.event_time_ms,
        (quote.ask - quote.bid) / quote.mid,
        Decimal("0.90"),
        Decimal("0.10"),
        Decimal("0.95"),
        Decimal("0.99"),
    )


class Execution:
    def __init__(self):
        self.calls = []

    def submit(self, **kwargs):
        self.calls.append(kwargs)
        return type(
            "Attempt",
            (),
            {
                "order_id": "o1",
                "order_state": None,
                "broker_order_id": "b1",
                "broker_outcome": "ACCEPTED",
                "reasons": (),
            },
        )()


def factory(*, decision, quote, market, now_ms, instrument):
    intent = TradeIntent(
        "i1",
        "s",
        "1",
        "p",
        "EURUSD",
        "BUY",
        Decimal("0.01"),
        "MARKET",
        None,
        Decimal("1.0"),
        None,
        now_ms,
        now_ms + 60_000,
        Decimal("0.001"),
        Decimal("0.001"),
        decision.forecast.horizon_seconds,
        frozenset(decision.evidence_ids),
    )
    context = AdmissionContext(
        now_ms,
        quote,
        decision.forecast,
        market,
        PortfolioState(
            Decimal("10000"),
            Decimal("0"),
            Decimal("0.001"),
            Decimal("0"),
            0,
            Decimal("0"),
            Decimal("0.001"),
            False,
        ),
        Decimal("0.0001"),
        Decimal("0.0001"),
    )
    return intent, context


def test_node_orchestrates_strategy_and_events_without_execution():
    bus = EventBus()
    node = TradingNode(
        config=RuntimeConfig(allow_execution=False),
        market_data=Feed(),
        controllers=(Controller(model(), ("EURUSD",)),),
        context_factory=factory,
        event_bus=bus,
        market_state_factory=market_state,
        clock=Clock(),
    )
    node.start()
    result = node.cycle()
    assert result
    assert any(type(e).__name__ == "ForecastEvent" for e in bus.history())
    assert any(type(e).__name__ == "OpportunityEvent" for e in bus.history())
    assert node.state.value == "RUNNING"


def test_node_executes_only_when_explicitly_enabled():
    execution = Execution()
    node = TradingNode(
        config=RuntimeConfig(allow_execution=True, estimated_cost_fraction=Decimal("0.0001"), safety_margin_fraction=Decimal("0.0001")),
        market_data=Feed(),
        controllers=(Controller(model(), ("EURUSD",)),),
        context_factory=factory,
        execution=execution,
        market_state_factory=market_state,
        clock=Clock(),
    )
    node.start()
    node.cycle()
    assert len(execution.calls) == 1
