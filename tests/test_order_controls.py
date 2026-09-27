from dataclasses import dataclass
import pytest

from apps.execution_gateway.order_controls import DemoOrderControls
from packages.demo_execution import SubmissionResult


@dataclass
class Order:
    state: str
    broker_order_id: str | None


class Repo:
    def __init__(self, order):
        self.order = order
        self.cancel_requested = False
        self.recorded = None
    def get(self, order_id):
        return self.order
    def mark_cancel_requested(self, order_id):
        self.cancel_requested = True
    def record_cancellation(self, order_id, result):
        self.recorded = result


class Broker:
    def cancel(self, broker_order_id):
        return SubmissionResult("ACCEPTED", broker_order_id=broker_order_id)


def test_cancel_is_durable_then_broker_confirmed():
    repo = Repo(Order("ACKNOWLEDGED", "42"))
    result = DemoOrderControls(repo, Broker()).cancel("o1")
    assert result.allowed
    assert repo.cancel_requested
    assert repo.recorded.outcome == "ACCEPTED"


def test_unknown_order_cannot_be_cancelled_blindly():
    repo = Repo(Order("UNKNOWN", "42"))
    result = DemoOrderControls(repo, Broker()).cancel("o1")
    assert not result.allowed
    assert result.outcome is None
    assert "UNKNOWN_ORDER_STATE_REQUIRES_TRUTH" in result.reasons
