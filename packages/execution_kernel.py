"""Deterministic execution orchestration.

The kernel is the narrow bridge between an approved TradeIntent and a broker adapter.
It creates durable intent state before touching the broker, submits at most once for a
given client-order identity, treats submission ambiguity as UNKNOWN, and never creates
a fill from an acknowledgement.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .demo_execution import SubmissionRequest, SubmissionResult, deterministic_client_order_id
from .models import AdmissionContext, Decision, InstrumentSpec, OrderState, TradeIntent
from .policy import AdmissionPolicy
from .risk_engine import DeterministicRiskEngine, RiskDecision


class DurableOrderRepository(Protocol):
    def ensure_intended(self, intent: TradeIntent, client_order_id: str): ...
    def mark_submitting(self, order_id: str): ...
    def record_submission(self, order_id: str, result: SubmissionResult): ...


class SubmissionAdapter(Protocol):
    def submit(self, request: SubmissionRequest) -> SubmissionResult: ...


class TruthAdapter(Protocol):
    def lookup_by_client_order_id(self, client_order_id: str) -> SubmissionResult | None: ...


@dataclass(frozen=True)
class ExecutionAttempt:
    decision: str
    client_order_id: str
    order_id: str | None
    order_state: OrderState | None
    risk: RiskDecision | None
    reasons: tuple[str, ...]
    broker_order_id: str | None = None
    broker_outcome: str | None = None


class ExecutionKernel:
    def __init__(self, *, policy: AdmissionPolicy | None = None, risk_engine: DeterministicRiskEngine | None = None) -> None:
        self.policy = policy or AdmissionPolicy()
        self.risk_engine = risk_engine or DeterministicRiskEngine()

    def execute(
        self,
        *,
        intent: TradeIntent,
        context: AdmissionContext,
        instrument: InstrumentSpec,
        repository: DurableOrderRepository,
        broker: SubmissionAdapter,
    ) -> ExecutionAttempt:
        client_order_id = deterministic_client_order_id(intent)
        decision, policy_reasons = self.policy.evaluate(context)
        if decision != Decision.APPROVE:
            return ExecutionAttempt("DENIED_POLICY", client_order_id, None, None, None, tuple(policy_reasons))

        risk = self.risk_engine.evaluate(intent=intent, context=context, instrument=instrument)
        if not risk.approved:
            return ExecutionAttempt("DENIED_RISK", client_order_id, None, None, risk, risk.reasons)

        durable = repository.ensure_intended(intent, client_order_id)
        terminal = {"FILLED", "REJECTED", "CANCELED", "CANCELLED"}
        if durable.state in terminal:
            return ExecutionAttempt(
                "ALREADY_TERMINAL", client_order_id, durable.order_id, self._state(durable.state), risk, (),
                durable.broker_order_id, "ACCEPTED" if durable.state == "FILLED" else durable.state,
            )

        if durable.state in {"SUBMITTED", "ACKNOWLEDGED", "PARTIALLY_FILLED", "UNKNOWN", "RECONCILING", "FREEZE"}:
            return ExecutionAttempt(
                "RECOVERY_REQUIRED", client_order_id, durable.order_id,
                OrderState.UNKNOWN if durable.state in {"UNKNOWN", "RECONCILING", "FREEZE"} else OrderState.ACCEPTED,
                risk, ("EXISTING_NONTERMINAL_ORDER",), durable.broker_order_id, None,
            )

        repository.mark_submitting(durable.order_id)
        request = SubmissionRequest(
            client_order_id=client_order_id,
            intent_id=intent.intent_id,
            symbol=intent.symbol,
            side=intent.side,
            quantity=intent.quantity,
            order_type=intent.order_type,
            limit_price=intent.limit_price,
            stop_price=intent.stop_price,
            target_price=intent.target_price,
        )
        try:
            result = broker.submit(request)
        except Exception:
            result = SubmissionResult("UNKNOWN", reason="broker_submission_exception")
            repository.record_submission(durable.order_id, result)
            return ExecutionAttempt("UNKNOWN", client_order_id, durable.order_id, OrderState.UNKNOWN, risk, ("BROKER_SUBMISSION_EXCEPTION",))

        persisted = repository.record_submission(durable.order_id, result)
        state = {"UNKNOWN": OrderState.UNKNOWN, "REJECTED": OrderState.REJECTED, "ACCEPTED": OrderState.ACCEPTED}.get(result.outcome)
        if state is None:
            raise ValueError(f"unsupported broker submission outcome:{result.outcome}")
        return ExecutionAttempt(
            "SUBMITTED" if result.outcome == "ACCEPTED" else result.outcome,
            client_order_id,
            persisted.order_id,
            state,
            risk,
            () if result.outcome != "REJECTED" else (result.reason or "BROKER_REJECTED",),
            persisted.broker_order_id,
            result.outcome,
        )

    @staticmethod
    def recover_unknown(*, order_id: str, client_order_id: str, repository: DurableOrderRepository, truth: TruthAdapter) -> SubmissionResult:
        """Resolve UNKNOWN from broker truth and persist it without submitting again."""
        order_id = order_id.strip()
        client_order_id = client_order_id.strip()
        if not order_id or not client_order_id:
            raise ValueError("order_id and client_order_id are required")
        result = truth.lookup_by_client_order_id(client_order_id)
        if result is None or result.outcome == "UNKNOWN":
            raise RuntimeError(f"unresolved_unknown_order:{client_order_id}")
        repository.record_submission(order_id, result)
        return result

    @staticmethod
    def _state(value: str) -> OrderState | None:
        mapping = {
            "FILLED": OrderState.FILLED,
            "REJECTED": OrderState.REJECTED,
            "CANCELED": OrderState.CANCELED,
            "CANCELLED": OrderState.CANCELED,
            "PARTIALLY_FILLED": OrderState.PARTIAL,
            "ACKNOWLEDGED": OrderState.ACCEPTED,
            "SUBMITTED": OrderState.SUBMITTING,
            "INTENDED": OrderState.AUTHORIZED,
            "UNKNOWN": OrderState.UNKNOWN,
            "RECONCILING": OrderState.RECONCILING,
            "FREEZE": OrderState.FREEZE,
        }
        return mapping.get(value)


__all__ = ["DurableOrderRepository", "ExecutionAttempt", "ExecutionKernel", "SubmissionAdapter", "TruthAdapter"]
