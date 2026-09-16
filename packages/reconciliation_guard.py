"""Fail-closed validation of broker snapshots before reconciliation.

A broker snapshot is evidence, not truth, until it passes structural integrity checks.
Duplicate client order identifiers or duplicate position instruments are ambiguous and
therefore force a freeze rather than allowing dict construction to silently discard data.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .broker_truth import BrokerSnapshot, ReconciliationOutcome


@dataclass(frozen=True)
class SnapshotIntegrity:
    valid: bool
    reasons: tuple[str, ...]


def validate_snapshot(snapshot: BrokerSnapshot) -> SnapshotIntegrity:
    reasons: list[str] = []

    client_ids = [o.client_order_id for o in snapshot.orders]
    duplicate_clients = sorted({cid for cid in client_ids if client_ids.count(cid) > 1})
    reasons.extend(f"duplicate_broker_client_order_id:{cid}" for cid in duplicate_clients)

    broker_order_ids = [o.broker_order_id for o in snapshot.orders]
    duplicate_broker_orders = sorted({oid for oid in broker_order_ids if broker_order_ids.count(oid) > 1})
    reasons.extend(f"duplicate_broker_order_id:{oid}" for oid in duplicate_broker_orders)

    position_instruments = [p.instrument for p in snapshot.positions]
    duplicate_positions = sorted({i for i in position_instruments if position_instruments.count(i) > 1})
    reasons.extend(f"duplicate_broker_position_instrument:{instrument}" for instrument in duplicate_positions)

    for order in snapshot.orders:
        if not order.client_order_id:
            reasons.append("empty_broker_client_order_id")
        if not order.broker_order_id:
            reasons.append("empty_broker_order_id")
        if not order.instrument:
            reasons.append("empty_broker_order_instrument")
        if order.filled_quantity < Decimal("0"):
            reasons.append(f"negative_broker_filled_quantity:{order.broker_order_id}")

    for position in snapshot.positions:
        if not position.instrument:
            reasons.append("empty_broker_position_instrument")

    return SnapshotIntegrity(not reasons, tuple(sorted(set(reasons))))


def guarded_outcome(snapshot: BrokerSnapshot, outcome: ReconciliationOutcome) -> ReconciliationOutcome:
    integrity = validate_snapshot(snapshot)
    if integrity.valid:
        return outcome
    reasons = tuple(sorted(set(outcome.position_drift + integrity.reasons)))
    return ReconciliationOutcome(
        status="FREEZE",
        freeze_required=True,
        results=outcome.results,
        position_drift=reasons,
    )
