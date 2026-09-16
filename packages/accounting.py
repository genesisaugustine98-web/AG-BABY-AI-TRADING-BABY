"""Broker-confirmed fill accounting and deterministic position reduction.

Only broker-confirmed fills are admissible. Submission acknowledgements, theoretical
fills, and unresolved UNKNOWN outcomes must never create account state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Iterable

from .execution_ledger import AppendOnlyLedger, LedgerEvent


@dataclass(frozen=True)
class BrokerConfirmedFill:
    fill_id: str
    broker_order_id: str
    client_order_id: str
    instrument: str
    side: str
    quantity: Decimal
    price: Decimal
    occurred_at: datetime
    broker: str
    confirmed: bool = True

    def signed_quantity(self) -> Decimal:
        side = self.side.upper()
        if side == "BUY":
            return self.quantity
        if side == "SELL":
            return -self.quantity
        raise ValueError(f"unsupported fill side: {self.side}")

    def validate(self) -> None:
        if not self.fill_id:
            raise ValueError("fill_id is required")
        if not self.broker_order_id:
            raise ValueError("broker_order_id is required")
        if not self.client_order_id:
            raise ValueError("client_order_id is required")
        if not self.instrument:
            raise ValueError("instrument is required")
        if self.quantity <= 0:
            raise ValueError("fill quantity must be positive")
        if self.price <= 0:
            raise ValueError("fill price must be positive")
        if not self.confirmed:
            raise ValueError("unconfirmed fill cannot enter accounting")
        self.signed_quantity()


@dataclass(frozen=True)
class FillAccountResult:
    event: LedgerEvent | None
    duplicate: bool
    position: "PositionState"


@dataclass(frozen=True)
class PositionState:
    instrument: str
    net_quantity: Decimal = Decimal("0")
    average_price: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")


@dataclass
class PositionBook:
    """Reduce confirmed fills into positions using exact Decimal arithmetic."""

    positions: dict[str, PositionState] = field(default_factory=dict)

    def apply(self, fill: BrokerConfirmedFill) -> PositionState:
        fill.validate()
        current = self.positions.get(fill.instrument, PositionState(fill.instrument))
        delta = fill.signed_quantity()
        qty = current.net_quantity

        if qty == 0:
            updated = PositionState(fill.instrument, delta, fill.price, current.realized_pnl)
            self.positions[fill.instrument] = updated
            return updated

        same_direction = (qty > 0 and delta > 0) or (qty < 0 and delta < 0)
        if same_direction:
            total_abs = abs(qty) + abs(delta)
            avg = ((abs(qty) * current.average_price) + (abs(delta) * fill.price)) / total_abs
            updated = PositionState(fill.instrument, qty + delta, avg, current.realized_pnl)
            self.positions[fill.instrument] = updated
            return updated

        closing = min(abs(qty), abs(delta))
        pnl = closing * (fill.price - current.average_price) * (Decimal("1") if qty > 0 else Decimal("-1"))
        remaining = qty + delta
        realized = current.realized_pnl + pnl

        if remaining == 0:
            updated = PositionState(fill.instrument, Decimal("0"), Decimal("0"), realized)
        elif (qty > 0 and remaining > 0) or (qty < 0 and remaining < 0):
            updated = PositionState(fill.instrument, remaining, current.average_price, realized)
        else:
            updated = PositionState(fill.instrument, remaining, fill.price, realized)

        self.positions[fill.instrument] = updated
        return updated


@dataclass
class ConfirmedFillProcessor:
    """Idempotently ledger confirmed fills, then reduce them into account state."""

    ledger: AppendOnlyLedger
    positions: PositionBook = field(default_factory=PositionBook)
    seen_fill_ids: set[str] = field(default_factory=set)

    def process(self, fill: BrokerConfirmedFill) -> FillAccountResult:
        fill.validate()
        if fill.fill_id in self.seen_fill_ids:
            return FillAccountResult(None, True, self.positions.positions[fill.instrument])

        payload = {
            "fill_id": fill.fill_id,
            "broker_order_id": fill.broker_order_id,
            "client_order_id": fill.client_order_id,
            "instrument": fill.instrument,
            "side": fill.side.upper(),
            "quantity": str(fill.quantity),
            "price": str(fill.price),
            "occurred_at": fill.occurred_at.isoformat(),
            "broker": fill.broker,
            "confirmed": fill.confirmed,
        }
        event = self.ledger.append(
            event_id=f"FILL:{fill.fill_id}",
            event_type="BROKER_CONFIRMED_FILL",
            correlation_id=fill.client_order_id,
            payload=payload,
            occurred_at=fill.occurred_at,
        )
        position = self.positions.apply(fill)
        self.seen_fill_ids.add(fill.fill_id)
        return FillAccountResult(event, False, position)

    def process_many(self, fills: Iterable[BrokerConfirmedFill]) -> list[FillAccountResult]:
        return [self.process(fill) for fill in fills]


def execution_tca(arrival_price: Decimal | None, fills: Iterable[BrokerConfirmedFill]) -> dict[str, Decimal | None]:
    """Compute fill-only TCA; unavailable reference data remains UNKNOWN (None)."""
    confirmed = list(fills)
    if not confirmed:
        return {"filled_quantity": Decimal("0"), "execution_vwap": None, "slippage_price": None}
    for fill in confirmed:
        fill.validate()
    total_qty = sum((fill.quantity for fill in confirmed), Decimal("0"))
    vwap = sum((fill.quantity * fill.price for fill in confirmed), Decimal("0")) / total_qty
    slippage = None
    if arrival_price is not None:
        # Positive = worse for BUY, better for SELL; callers can sign-normalize by order side.
        first_side = confirmed[0].side.upper()
        direction = Decimal("1") if first_side == "BUY" else Decimal("-1")
        slippage = (vwap - arrival_price) * direction
    return {"filled_quantity": total_qty, "execution_vwap": vwap, "slippage_price": slippage}
