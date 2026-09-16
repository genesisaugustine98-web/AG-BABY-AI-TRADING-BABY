"""Deterministic append-only execution ledger primitives.

The ledger is deliberately broker-agnostic. Persistence can be backed by Postgres,
while these invariants remain testable without network access.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class LedgerEvent:
    event_id: str
    occurred_at: str
    event_type: str
    correlation_id: str
    payload: dict[str, Any]
    previous_event_hash: str | None
    event_hash: str


@dataclass
class AppendOnlyLedger:
    events: list[LedgerEvent] = field(default_factory=list)

    @staticmethod
    def _canonical(payload: dict[str, Any]) -> str:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)

    def append(
        self,
        *,
        event_id: str,
        event_type: str,
        correlation_id: str,
        payload: dict[str, Any],
        occurred_at: datetime | None = None,
    ) -> LedgerEvent:
        if any(event.event_id == event_id for event in self.events):
            raise ValueError(f"duplicate event_id: {event_id}")
        ts = (occurred_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
        previous = self.events[-1].event_hash if self.events else None
        body = {
            "event_id": event_id,
            "occurred_at": ts,
            "event_type": event_type,
            "correlation_id": correlation_id,
            "payload": payload,
            "previous_event_hash": previous,
        }
        digest = hashlib.sha256(self._canonical(body).encode()).hexdigest()
        event = LedgerEvent(
            event_id=event_id,
            occurred_at=ts,
            event_type=event_type,
            correlation_id=correlation_id,
            payload=dict(payload),
            previous_event_hash=previous,
            event_hash=digest,
        )
        self.events.append(event)
        return event

    def verify_chain(self) -> bool:
        previous: str | None = None
        for event in self.events:
            body = {
                "event_id": event.event_id,
                "occurred_at": event.occurred_at,
                "event_type": event.event_type,
                "correlation_id": event.correlation_id,
                "payload": event.payload,
                "previous_event_hash": previous,
            }
            expected = hashlib.sha256(self._canonical(body).encode()).hexdigest()
            if event.previous_event_hash != previous or event.event_hash != expected:
                return False
            previous = event.event_hash
        return True


@dataclass(frozen=True)
class BrokerOrderTruth:
    broker_order_id: str
    client_order_id: str
    instrument: str
    state: str
    filled_quantity: Decimal


@dataclass(frozen=True)
class InternalOrderTruth:
    order_id: str
    client_order_id: str
    instrument: str
    state: str
    filled_quantity: Decimal


@dataclass(frozen=True)
class ReconciliationResult:
    status: str
    drift_count: int
    reasons: tuple[str, ...]


def reconcile_order(internal: InternalOrderTruth, broker: BrokerOrderTruth) -> ReconciliationResult:
    reasons: list[str] = []
    if internal.client_order_id != broker.client_order_id:
        reasons.append("client_order_id_mismatch")
    if internal.instrument != broker.instrument:
        reasons.append("instrument_mismatch")
    if internal.state != broker.state:
        reasons.append("state_mismatch")
    if internal.filled_quantity != broker.filled_quantity:
        reasons.append("filled_quantity_mismatch")
    if reasons:
        return ReconciliationResult("DRIFT", len(reasons), tuple(reasons))
    return ReconciliationResult("MATCHED", 0, ())


def reconcile_missing_broker_order(internal: InternalOrderTruth) -> ReconciliationResult:
    """Missing broker truth is UNKNOWN, never proof of cancellation/fill."""
    return ReconciliationResult("UNKNOWN", 1, ("broker_order_not_found",))
