"""Demo-only order lifecycle orchestration with explicit UNKNOWN handling.

This module never talks to a real broker. It defines the deterministic control flow
that a broker adapter must satisfy before any live implementation is considered.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from typing import Protocol

from .models import OrderState, TradeIntent
from .order_state import OrderStateMachine


@dataclass(frozen=True)
class SubmissionRequest:
    client_order_id: str
    intent_id: str
    symbol: str
    side: str
    quantity: Decimal
    order_type: str
    limit_price: Decimal | None


@dataclass(frozen=True)
class SubmissionResult:
    outcome: str  # ACCEPTED, REJECTED, UNKNOWN
    broker_order_id: str | None = None
    filled_quantity: Decimal = Decimal("0")
    reason: str | None = None


class DemoSubmissionAdapter(Protocol):
    def submit(self, request: SubmissionRequest) -> SubmissionResult: ...


class DemoTruthAdapter(Protocol):
    def lookup_by_client_order_id(self, client_order_id: str) -> SubmissionResult | None: ...


def deterministic_client_order_id(intent: TradeIntent) -> str:
    """Stable, bounded identifier; identical intent_id always yields identical ID."""
    digest = sha256(intent.intent_id.encode("utf-8")).hexdigest()[:20]
    return f"AGDEMO-{digest}"


class DemoOrderLifecycle:
    """Submit once, then require reconciliation for ambiguity."""

    def __init__(self, submission: DemoSubmissionAdapter, truth: DemoTruthAdapter):
        self.submission = submission
        self.truth = truth

    def submit_once(self, intent: TradeIntent) -> tuple[str, SubmissionResult]:
        client_order_id = deterministic_client_order_id(intent)
        machine = OrderStateMachine(OrderState.AUTHORIZED)
        machine.transition(OrderState.SUBMITTING)
        result = self.submission.submit(
            SubmissionRequest(
                client_order_id=client_order_id,
                intent_id=intent.intent_id,
                symbol=intent.symbol,
                side=intent.side,
                quantity=intent.quantity,
                order_type=intent.order_type,
                limit_price=intent.limit_price,
            )
        )
        if result.outcome == "ACCEPTED":
            return client_order_id, result
        if result.outcome == "REJECTED":
            return client_order_id, result
        if result.outcome == "UNKNOWN":
            machine.transition(OrderState.UNKNOWN)
            return client_order_id, result
        raise ValueError(f"unsupported broker outcome: {result.outcome}")

    def reconcile_unknown(self, client_order_id: str) -> SubmissionResult:
        result = self.truth.lookup_by_client_order_id(client_order_id)
        if result is None:
            raise RuntimeError("UNKNOWN order remains unresolved; trading must stay frozen")
        if result.outcome == "UNKNOWN":
            raise RuntimeError("broker truth is still UNKNOWN; trading must stay frozen")
        return result
