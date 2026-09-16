"""Broker-truth contracts and fail-closed reconciliation orchestration.

This module is broker-agnostic. Concrete adapters may query MT5 or another broker,
but the reconciler never interprets missing/ambiguous broker state as a safe state.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from .execution_ledger import (
    BrokerOrderTruth,
    InternalOrderTruth,
    ReconciliationResult,
    reconcile_missing_broker_order,
    reconcile_order,
)


@dataclass(frozen=True)
class BrokerPositionTruth:
    instrument: str
    net_quantity: Decimal


@dataclass(frozen=True)
class BrokerSnapshot:
    orders: tuple[BrokerOrderTruth, ...]
    positions: tuple[BrokerPositionTruth, ...]
    captured_at: str


class BrokerTruthAdapter(Protocol):
    def snapshot(self) -> BrokerSnapshot: ...


@dataclass(frozen=True)
class ReconciliationOutcome:
    status: str
    freeze_required: bool
    results: tuple[ReconciliationResult, ...]
    position_drift: tuple[str, ...]


class Reconciler:
    """Compare durable internal truth against a broker snapshot.

    Any DRIFT or UNKNOWN outcome requires a freeze. MATCHED is the only state
    that permits reconciliation to report a clean result.
    """

    def reconcile(
        self,
        internal_orders: tuple[InternalOrderTruth, ...],
        internal_positions: tuple[BrokerPositionTruth, ...],
        broker: BrokerSnapshot,
    ) -> ReconciliationOutcome:
        broker_by_client = {o.client_order_id: o for o in broker.orders}
        results: list[ReconciliationResult] = []
        freeze = False

        for internal in internal_orders:
            external = broker_by_client.get(internal.client_order_id)
            if external is None:
                result = reconcile_missing_broker_order(internal)
            else:
                result = reconcile_order(internal, external)
            results.append(result)
            if result.status != "MATCHED":
                freeze = True

        internal_pos = {p.instrument: p.net_quantity for p in internal_positions}
        broker_pos = {p.instrument: p.net_quantity for p in broker.positions}
        position_reasons: list[str] = []
        for instrument in sorted(set(internal_pos) | set(broker_pos)):
            if internal_pos.get(instrument, Decimal("0")) != broker_pos.get(instrument, Decimal("0")):
                position_reasons.append(f"position_mismatch:{instrument}")
        if position_reasons:
            freeze = True

        status = "MATCHED" if not freeze else "FREEZE"
        return ReconciliationOutcome(status, freeze, tuple(results), tuple(position_reasons))
