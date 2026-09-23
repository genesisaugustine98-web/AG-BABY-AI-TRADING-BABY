"""Truth-first demo order control operations.

Cancel/replace/expiry commands never bypass the durable internal-order state. The adapter
remains demo-only and broker truth is required before mutating an ambiguous order.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from packages.execution_commands import CommandType, validate_order_command
from packages.models import OrderState
from packages.demo_execution import SubmissionResult


@dataclass(frozen=True)
class ControlResult:
    allowed: bool
    outcome: SubmissionResult | None
    reasons: tuple[str, ...]


class OrderRepository(Protocol):
    def get(self, order_id: str): ...
    def mark_cancel_requested(self, order_id: str): ...
    def record_cancellation(self, order_id: str, result: SubmissionResult): ...


class BrokerControlAdapter(Protocol):
    def cancel(self, broker_order_id: str) -> SubmissionResult: ...


_DURABLE_TO_MODEL_STATE = {
    "INTENDED": OrderState.AUTHORIZED,
    "SUBMITTED": OrderState.SUBMITTING,
    "ACKNOWLEDGED": OrderState.ACCEPTED,
    "PARTIALLY_FILLED": OrderState.PARTIAL,
    "FILLED": OrderState.FILLED,
    "REJECTED": OrderState.REJECTED,
    "CANCELLED": OrderState.CANCELED,
    "UNKNOWN": OrderState.UNKNOWN,
    "RECONCILING": OrderState.RECONCILING,
    "FREEZE": OrderState.FREEZE,
}


class DemoOrderControls:
    def __init__(self, repository: OrderRepository, broker: BrokerControlAdapter):
        self.repository = repository
        self.broker = broker

    def cancel(self, order_id: str) -> ControlResult:
        order = self.repository.get(order_id)
        state = _DURABLE_TO_MODEL_STATE.get(str(order.state).upper())
        if state is None:
            return ControlResult(False, None, ("UNSUPPORTED_DURABLE_ORDER_STATE",))
        validation = validate_order_command(
            command=CommandType.CANCEL,
            state=state,
            broker_order_id=order.broker_order_id,
        )
        if not validation.allowed:
            return ControlResult(False, None, validation.reasons)

        self.repository.mark_cancel_requested(order_id)
        try:
            result = self.broker.cancel(str(order.broker_order_id))
        except Exception as exc:
            return ControlResult(False, SubmissionResult("UNKNOWN", broker_order_id=order.broker_order_id, reason=type(exc).__name__), ("CANCEL_BROKER_EXCEPTION",))
        self.repository.record_cancellation(order_id, result)
        return ControlResult(result.outcome == "ACCEPTED", result, () if result.outcome == "ACCEPTED" else ("BROKER_CANCEL_REJECTED",))


__all__ = ["ControlResult", "DemoOrderControls"]
