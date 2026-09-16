from decimal import Decimal

import pytest

from packages.demo_execution import (
    DemoOrderLifecycle,
    SubmissionRequest,
    SubmissionResult,
    deterministic_client_order_id,
    lifecycle_state,
)
from packages.models import OrderState, TradeIntent


def intent(intent_id="intent-1"):
    return TradeIntent(
        intent_id=intent_id,
        strategy_id="demo",
        strategy_version="1",
        policy_version="1",
        symbol="USDJPY",
        side="BUY",
        quantity=Decimal("1"),
        order_type="MARKET",
        limit_price=None,
        stop_price=Decimal("0"),
        target_price=None,
        created_at_ms=1,
        expires_at_ms=1000,
        max_slippage_fraction=Decimal("0.001"),
        risk_fraction=Decimal("0.001"),
        horizon_seconds=60,
    )


class Submitter:
    def __init__(self, result):
        self.result = result
        self.requests = []

    def submit(self, request: SubmissionRequest):
        self.requests.append(request)
        return self.result


class Truth:
    def __init__(self, result):
        self.result = result
        self.ids = []

    def lookup_by_client_order_id(self, client_order_id):
        self.ids.append(client_order_id)
        return self.result


def test_client_order_id_is_deterministic():
    assert deterministic_client_order_id(intent()) == deterministic_client_order_id(intent())
    assert deterministic_client_order_id(intent("a")) != deterministic_client_order_id(intent("b"))


def test_unknown_is_not_retried_and_requires_truth():
    submitter = Submitter(SubmissionResult("UNKNOWN", reason="timeout"))
    truth = Truth(None)
    lifecycle = DemoOrderLifecycle(submitter, truth)

    client_id, result, state = lifecycle.submit_once(intent())
    assert result.outcome == "UNKNOWN"
    assert state is OrderState.UNKNOWN
    assert len(submitter.requests) == 1
    assert client_id == submitter.requests[0].client_order_id
    with pytest.raises(RuntimeError, match="remains unresolved"):
        lifecycle.reconcile_unknown(client_id)


def test_unknown_resolves_from_broker_truth():
    submitter = Submitter(SubmissionResult("UNKNOWN"))
    truth = Truth(SubmissionResult("ACCEPTED", broker_order_id="broker-1"))
    lifecycle = DemoOrderLifecycle(submitter, truth)
    client_id, _, _ = lifecycle.submit_once(intent())

    resolved = lifecycle.reconcile_unknown(client_id)
    assert resolved.outcome == "ACCEPTED"
    assert resolved.broker_order_id == "broker-1"
    assert truth.ids == [client_id]


def test_rejected_does_not_become_fill():
    submitter = Submitter(SubmissionResult("REJECTED", reason="demo rejection"))
    truth = Truth(None)
    lifecycle = DemoOrderLifecycle(submitter, truth)

    _, result, state = lifecycle.submit_once(intent())
    assert result.outcome == "REJECTED"
    assert state is OrderState.REJECTED
    assert truth.ids == []


def test_partial_and_full_fill_states_are_explicit():
    requested = Decimal("2")
    assert lifecycle_state(SubmissionResult("ACCEPTED"), requested) is OrderState.ACCEPTED
    assert lifecycle_state(SubmissionResult("ACCEPTED", filled_quantity=Decimal("1")), requested) is OrderState.PARTIAL
    assert lifecycle_state(SubmissionResult("ACCEPTED", filled_quantity=Decimal("2")), requested) is OrderState.FILLED
    with pytest.raises(ValueError, match="outside requested"):
        lifecycle_state(SubmissionResult("ACCEPTED", filled_quantity=Decimal("3")), requested)
