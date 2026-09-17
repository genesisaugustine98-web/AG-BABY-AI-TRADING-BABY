"""Broker-confirmed fill ingestion and deterministic position accounting.

This module never creates a fill from an order acknowledgement. A fill must carry
broker-confirmed identity, quantity, price, side, and execution time. Fills are kept
immutable and positions are a deterministic projection of the confirmed fill set.

Realized P&L is expressed in quote-currency units under the convention that quantity
is the traded base quantity and price is quote currency per base unit. Converting that
amount into an account currency is deliberately outside this module.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Mapping


_VALID_SIDES = {"BUY", "SELL"}


def _decimal(value: Decimal | str | int | float) -> Decimal:
    result = value if isinstance(value, Decimal) else Decimal(str(value))
    if not result.is_finite():
        raise ValueError("decimal value must be finite")
    return result


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
    return value.strip()


@dataclass(frozen=True)
class BrokerConfirmedFill:
    fill_id: str
    order_id: str
    instrument: str
    side: str
    quantity: Decimal
    price: Decimal
    filled_at: str
    broker_fill_id: str | None = None
    broker_order_id: str | None = None
    venue: str | None = None
    commission: Decimal = Decimal("0")
    financing: Decimal = Decimal("0")
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "fill_id", _required_text(self.fill_id, "fill_id"))
        object.__setattr__(self, "order_id", _required_text(self.order_id, "order_id"))
        object.__setattr__(self, "instrument", _required_text(self.instrument, "instrument"))
        object.__setattr__(self, "filled_at", _required_text(self.filled_at, "filled_at"))
        side = _required_text(self.side, "side").upper()
        if side not in _VALID_SIDES:
            raise ValueError(f"unsupported side: {self.side!r}")
        object.__setattr__(self, "side", side)
        quantity = _decimal(self.quantity)
        price = _decimal(self.price)
        commission = _decimal(self.commission)
        financing = _decimal(self.financing)
        if quantity <= 0:
            raise ValueError("quantity must be > 0")
        if price <= 0:
            raise ValueError("price must be > 0")
        object.__setattr__(self, "quantity", quantity)
        object.__setattr__(self, "price", price)
        object.__setattr__(self, "commission", commission)
        object.__setattr__(self, "financing", financing)
        if self.broker_fill_id is not None:
            object.__setattr__(self, "broker_fill_id", _required_text(self.broker_fill_id, "broker_fill_id"))
        if self.broker_order_id is not None:
            object.__setattr__(self, "broker_order_id", _required_text(self.broker_order_id, "broker_order_id"))
        if self.venue is not None:
            object.__setattr__(self, "venue", _required_text(self.venue, "venue"))
        object.__setattr__(self, "metadata", dict(self.metadata))

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "fill_id": self.fill_id,
            "order_id": self.order_id,
            "instrument": self.instrument,
            "side": self.side,
            "quantity": str(self.quantity),
            "price": str(self.price),
            "filled_at": self.filled_at,
            "broker_fill_id": self.broker_fill_id,
            "broker_order_id": self.broker_order_id,
            "venue": self.venue,
            "commission": str(self.commission),
            "financing": str(self.financing),
            "metadata": self.metadata,
        }

    @property
    def fingerprint(self) -> str:
        raw = json.dumps(self.canonical_payload(), sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PositionState:
    instrument: str
    net_quantity: Decimal = Decimal("0")
    average_price: Decimal | None = None
    realized_pnl: Decimal = Decimal("0")
    financing_pnl: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        object.__setattr__(self, "net_quantity", _decimal(self.net_quantity))
        object.__setattr__(self, "realized_pnl", _decimal(self.realized_pnl))
        object.__setattr__(self, "financing_pnl", _decimal(self.financing_pnl))
        if self.average_price is not None:
            average = _decimal(self.average_price)
            if average <= 0:
                raise ValueError("average_price must be > 0 when present")
            object.__setattr__(self, "average_price", average)
        if self.net_quantity == 0 and self.average_price is not None:
            raise ValueError("flat position must have no average_price")
        if self.net_quantity != 0 and self.average_price is None:
            raise ValueError("open position must have average_price")


def apply_fill(position: PositionState, fill: BrokerConfirmedFill) -> PositionState:
    """Apply one immutable broker-confirmed fill to a position projection."""
    if position.instrument != fill.instrument:
        raise ValueError("fill instrument does not match position instrument")

    signed_qty = fill.quantity if fill.side == "BUY" else -fill.quantity
    net = position.net_quantity
    realized = position.realized_pnl
    financing = position.financing_pnl + fill.financing

    if net == 0:
        return PositionState(
            instrument=position.instrument,
            net_quantity=signed_qty,
            average_price=fill.price,
            realized_pnl=realized,
            financing_pnl=financing,
        )

    same_direction = (net > 0 and signed_qty > 0) or (net < 0 and signed_qty < 0)
    if same_direction:
        total_qty = abs(net) + abs(signed_qty)
        weighted_average = (abs(net) * position.average_price + abs(signed_qty) * fill.price) / total_qty
        return PositionState(
            instrument=position.instrument,
            net_quantity=net + signed_qty,
            average_price=weighted_average,
            realized_pnl=realized,
            financing_pnl=financing,
        )

    closing_qty = min(abs(net), abs(signed_qty))
    assert position.average_price is not None
    if net > 0:
        realized += closing_qty * (fill.price - position.average_price)
    else:
        realized += closing_qty * (position.average_price - fill.price)

    remaining = net + signed_qty
    if remaining == 0:
        return PositionState(
            instrument=position.instrument,
            net_quantity=Decimal("0"),
            average_price=None,
            realized_pnl=realized,
            financing_pnl=financing,
        )

    if (net > 0 and remaining > 0) or (net < 0 and remaining < 0):
        return PositionState(
            instrument=position.instrument,
            net_quantity=remaining,
            average_price=position.average_price,
            realized_pnl=realized,
            financing_pnl=financing,
        )

    # Reversal: the unpaired remainder opens at the reversing fill price.
    return PositionState(
        instrument=position.instrument,
        net_quantity=remaining,
        average_price=fill.price,
        realized_pnl=realized,
        financing_pnl=financing,
    )


@dataclass(frozen=True)
class IngestResult:
    status: str
    fill: BrokerConfirmedFill
    position: PositionState


@dataclass
class FillAccountingEngine:
    """Idempotent confirmed-fill store with deterministic position projection."""

    fills: dict[str, BrokerConfirmedFill] = field(default_factory=dict)

    def ingest(self, fill: BrokerConfirmedFill) -> IngestResult:
        existing = self.fills.get(fill.fill_id)
        if existing is not None:
            if existing.fingerprint != fill.fingerprint:
                raise ValueError(f"fill_id_conflict:{fill.fill_id}")
            return IngestResult("DUPLICATE", fill, self.position(fill.instrument))
        self.fills[fill.fill_id] = fill
        return IngestResult("APPLIED", fill, self.position(fill.instrument))

    def position(self, instrument: str) -> PositionState:
        instrument = _required_text(instrument, "instrument")
        state = PositionState(instrument=instrument)
        ordered = sorted(
            (fill for fill in self.fills.values() if fill.instrument == instrument),
            key=lambda fill: (fill.filled_at, fill.fill_id),
        )
        for fill in ordered:
            state = apply_fill(state, fill)
        return state

    def positions(self) -> tuple[PositionState, ...]:
        instruments = sorted({fill.instrument for fill in self.fills.values()})
        return tuple(self.position(instrument) for instrument in instruments)


__all__ = [
    "BrokerConfirmedFill",
    "FillAccountingEngine",
    "IngestResult",
    "PositionState",
    "apply_fill",
]
