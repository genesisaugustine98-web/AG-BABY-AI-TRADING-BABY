from decimal import Decimal

from apps.execution_gateway.runtime import DemoExecutionRuntime
from packages.models import (
    AdmissionContext,
    EventState,
    Forecast,
    InstrumentSpec,
    MarketState,
    PortfolioState,
    Quote,
    TradeIntent,
)


class Safety:
    def __init__(self, frozen=False):
        self.frozen = frozen

    def load_frozen(self):
        return self.frozen


class Reconciliation:
    def __init__(self, permitted):
        self.trading_permitted = permitted


class Kernel:
    def __init__(self):
        self.calls = 0

    def execute(self, **kwargs):
        self.calls += 1
        return "EXECUTED"


def intent():
    return TradeIntent(
        "i1", "s1", "v1", "p1", "USDJPY", "BUY",
        Decimal("0.1"), "MARKET", None, Decimal("149"),
        Decimal("152"), 1000, 5000, Decimal("0.001"),
        Decimal("0.001"), 300, frozenset(),
    )


def context():
    return AdmissionContext(
        2000,
        Quote("USDJPY", Decimal("150"), Decimal("150.002"), 1990, "demo"),
        Forecast("m", "1", 1000, 300, Decimal("0.002"), "fraction", Decimal("0.70"), Decimal("0.80"), Decimal("0.80")),
        MarketState(EventState.NORMAL, 10, Decimal("0.00001"), Decimal("0.9"), Decimal("0.1"), Decimal("0.95"), Decimal("0.95")),
        PortfolioState(Decimal("100000"), Decimal("0"), Decimal("0"), Decimal("1"), 0, Decimal("0"), Decimal("0"), False),
        Decimal("0.0001"),
        Decimal("0.0001"),
    )


def spec():
    return InstrumentSpec(
        "USDJPY", "USD", "JPY",
        Decimal("100000"), Decimal("0.001"), Decimal("0.001"),
        Decimal("1"), Decimal("0.01"), Decimal("100"), Decimal("0.01"),
    )


class Gateway:
    def _import(self):
        return object()


def runtime(permitted):
    return DemoExecutionRuntime(
        gateway=Gateway(),
        orders=object(),
        safety=Safety(False),
        kernel=Kernel(),
        reconciliation=Reconciliation(permitted),
    )


def test_runtime_denies_submission_until_fresh_clean_reconciliation():
    bot = runtime(False)
    result = bot.submit(intent=intent(), context=context(), instrument=spec())
    assert result.decision == "DENIED_RECONCILIATION_NOT_READY"
    assert bot.kernel.calls == 0


def test_runtime_allows_kernel_after_clean_reconciliation():
    bot = runtime(True)
    result = bot.submit(intent=intent(), context=context(), instrument=spec())
    assert result == "EXECUTED"
    assert bot.kernel.calls == 1


def test_runtime_persisted_freeze_still_wins_over_ready_reconciliation():
    bot = runtime(True)
    bot.safety.frozen = True
    result = bot.submit(intent=intent(), context=context(), instrument=spec())
    assert result.decision == "DENIED_FROZEN_CONTROL_STATE"
    assert bot.kernel.calls == 0
