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


@dataclass(frozen=True)
class ReplaceRequest:
    symbol: str
    side: str
    limit_price: Decimal
    stop_price: Decimal | None = None
    target_price: Decimal | None = None
    expires_at_ms: int = 0


class BrokerControlAdapter(Protocol):
    def cancel(self, broker_order_id: str) -> SubmissionResult: ...
    def replace(
        self,
        broker_order_id: str,
        *,
        symbol: str,
        side: str,
        limit_price: Decimal,
        stop_price: Decimal | None,
        target_price: Decimal | None,
        expires_at_ms: int = 0,
    ) -> SubmissionResult: ...
    def expire(self, broker_order_id: str) -> SubmissionResult: ...


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

    def replace(self, order_id: str, request: ReplaceRequest) -> ControlResult:
        order = self.repository.get(order_id)
        state = _DURABLE_TO_MODEL_STATE.get(str(order.state).upper())
        if state is None:
            return ControlResult(False, None, ("UNSUPPORTED_DURABLE_ORDER_STATE",))
        validation = validate_order_command(
            command=CommandType.REPLACE,
            state=state,
            broker_order_id=order.broker_order_id,
        )
        if not validation.allowed:
            return ControlResult(False, None, validation.reasons)
        if request.limit_price <= 0:
            return ControlResult(False, None, ("INVALID_REPLACEMENT_PRICE",))
        marker = getattr(self.repository, "mark_replace_requested", None)
        recorder = getattr(self.repository, "record_replacement", None)
        if not callable(marker) or not callable(recorder):
            return ControlResult(False, None, ("DURABLE_REPLACE_UNSUPPORTED",))
        marker(order_id, request.limit_price, request.stop_price, request.target_price, request.expires_at_ms)
        try:
            result = self.broker.replace(
                str(order.broker_order_id),
                symbol=str(order.instrument),
                side=str(order.side),
                limit_price=request.limit_price,
                stop_price=request.stop_price,
                target_price=request.target_price,
                expires_at_ms=request.expires_at_ms,
            )
        except Exception as exc:
            result = SubmissionResult("UNKNOWN", broker_order_id=order.broker_order_id, reason=type(exc).__name__)
        recorder(order_id, result)
        return ControlResult(result.outcome == "ACCEPTED", result, () if result.outcome == "ACCEPTED" else ("BROKER_REPLACE_NOT_CONFIRMED",))

    def expire(self, order_id: str) -> ControlResult:
        order = self.repository.get(order_id)
        state = _DURABLE_TO_MODEL_STATE.get(str(order.state).upper())
        if state is None:
            return ControlResult(False, None, ("UNSUPPORTED_DURABLE_ORDER_STATE",))
        validation = validate_order_command(
            command=CommandType.EXPIRE,
            state=state,
            broker_order_id=order.broker_order_id,
        )
        if not validation.allowed:
            return ControlResult(False, None, validation.reasons)
        marker = getattr(self.repository, "mark_expire_requested", None)
        recorder = getattr(self.repository, "record_expiration", None)
        if not callable(marker) or not callable(recorder):
            return ControlResult(False, None, ("DURABLE_EXPIRE_UNSUPPORTED",))
        marker(order_id)
        try:
            result = self.broker.expire(str(order.broker_order_id))
        except Exception as exc:
            result = SubmissionResult("UNKNOWN", broker_order_id=order.broker_order_id, reason=type(exc).__name__)
        recorder(order_id, result)
        return ControlResult(result.outcome == "ACCEPTED", result, () if result.outcome == "ACCEPTED" else ("BROKER_EXPIRE_NOT_CONFIRMED",))

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


__all__ = ["ControlResult", "DemoOrderControls", "ReplaceRequest"]
