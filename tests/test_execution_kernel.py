from decimal import Decimal

from packages.demo_execution import SubmissionResult
from packages.execution_kernel import ExecutionKernel
from packages.models import AdmissionContext, EventState, Forecast, InstrumentSpec, MarketState, PortfolioState, Quote, TradeIntent


class Repo:
    def __init__(self, state="INTENDED"):
        self.state = state
        self.calls = []
        self.order = type("O", (), {"order_id": "ord-1", "state": state, "broker_order_id": None})()

    def ensure_intended(self, intent, client_order_id):
        self.calls.append(("ensure", client_order_id))
        return self.order

    def mark_submitting(self, order_id):
        self.calls.append(("submitting", order_id))
        self.order.state = "SUBMITTED"
        return self.order

    def record_submission(self, order_id, result):
        self.calls.append(("record", result.outcome))
        if result.broker_order_id:
            self.order.broker_order_id = result.broker_order_id
        self.order.state = {"ACCEPTED": "ACKNOWLEDGED", "REJECTED": "REJECTED", "UNKNOWN": "UNKNOWN"}[result.outcome]
        return self.order


class Broker:
    def __init__(self, result=None, error=None):
        self.result = result or SubmissionResult("ACCEPTED", broker_order_id="mt5-9")
        self.error = error
        self.calls = []

    def submit(self, request):
        self.calls.append(request)
        if self.error:
            raise self.error
        return self.result


def intent():
    return TradeIntent("i1", "s1", "v1", "p1", "USDJPY", "BUY", Decimal("0.1"), "MARKET", None, Decimal("149"), Decimal("152"), 1000, 5000, Decimal("0.001"), Decimal("0.001"), 300, frozenset())


def context():
    return AdmissionContext(
        2000,
        Quote("USDJPY", Decimal("150"), Decimal("150.002"), 1990, "demo"),
        Forecast("m", "1", 1000, 300, Decimal("0.002"), "fraction", Decimal("0.70"), Decimal("0.80"), Decimal("0.80")),
        MarketState(EventState.NORMAL, 10, Decimal("0.00001"), Decimal("0.9"), Decimal("0.1"), Decimal("0.95"), Decimal("0.95")),
        PortfolioState(Decimal("100000"), Decimal("0"), Decimal("0.0"), Decimal("1"), 1, Decimal("0"), Decimal("0"), False),
        Decimal("0.0001"), Decimal("0.0001"),
    )


def spec():
    return InstrumentSpec("USDJPY", "USD", "JPY", Decimal("100000"), Decimal("0.001"), Decimal("0.001"), Decimal("1"), Decimal("0.01"), Decimal("100"), Decimal("0.01"))


def test_kernel_persists_before_submission_and_never_records_fill():
    repo = Repo()
    broker = Broker()
    result = ExecutionKernel().execute(intent=intent(), context=context(), instrument=spec(), repository=repo, broker=broker)
    assert result.decision == "SUBMITTED"
    assert result.broker_order_id == "mt5-9"
    assert [call[0] for call in repo.calls] == ["ensure", "submitting", "record"]
    assert len(broker.calls) == 1
    assert broker.calls[0].client_order_id.startswith("AGDEMO-")
    assert broker.calls[0].stop_price == Decimal("149")


def test_kernel_turns_submission_exception_into_unknown_without_retry():
    repo = Repo()
    broker = Broker(error=RuntimeError("terminal unavailable"))
    result = ExecutionKernel().execute(intent=intent(), context=context(), instrument=spec(), repository=repo, broker=broker)
    assert result.decision == "UNKNOWN"
    assert result.order_state.value == "UNKNOWN"
    assert broker.calls and len(broker.calls) == 1
    assert repo.calls[-1] == ("record", "UNKNOWN")


def test_kernel_refuses_to_resubmit_existing_nonterminal_order():
    repo = Repo(state="ACKNOWLEDGED")
    broker = Broker()
    result = ExecutionKernel().execute(intent=intent(), context=context(), instrument=spec(), repository=repo, broker=broker)
    assert result.decision == "RECOVERY_REQUIRED"
    assert broker.calls == []
