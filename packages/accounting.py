"""Compatibility facade for the canonical fill-accounting engine.

New code should import from ``packages.fill_accounting``. This module deliberately
keeps the historical API used by older tests/integrations while delegating all position
math and fill validation to the canonical deterministic engine, preventing two separate
accounting implementations from diverging.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Iterable

from .execution_ledger import AppendOnlyLedger, LedgerEvent
from .fill_accounting import BrokerConfirmedFill as CanonicalFill
from .fill_accounting import FillAccountingEngine, PositionState as CanonicalPosition, apply_fill


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

    def _canonical(self) -> CanonicalFill:
        return CanonicalFill(
            fill_id=self.fill_id,
            order_id=self.client_order_id,
            instrument=self.instrument,
            side=self.side,
            quantity=self.quantity,
            price=self.price,
            filled_at=self.occurred_at.isoformat(),
            broker_fill_id=self.fill_id,
            broker_order_id=self.broker_order_id,
            venue=self.broker,
            metadata={"legacy_api": True, "client_order_id": self.client_order_id},
        ) if self.confirmed else self._unconfirmed_placeholder()

    def _unconfirmed_placeholder(self) -> CanonicalFill:
        # Canonical construction is still strict; validation below handles the
        # historical confirmed=False semantic before any accounting occurs.
        return CanonicalFill(
            fill_id=self.fill_id,
            order_id=self.client_order_id,
            instrument=self.instrument,
            side=self.side,
            quantity=self.quantity,
            price=self.price,
            filled_at=self.occurred_at.isoformat(),
            broker_fill_id=self.fill_id,
            broker_order_id=self.broker_order_id,
            venue=self.broker,
            metadata={"legacy_api": True, "client_order_id": self.client_order_id},
        )

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
        self._canonical()


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


def _to_legacy(state: CanonicalPosition) -> PositionState:
    return PositionState(
        instrument=state.instrument,
        net_quantity=state.net_quantity,
        average_price=state.average_price if state.average_price is not None else Decimal("0"),
        realized_pnl=state.realized_pnl,
    )


@dataclass
class PositionBook:
    """Legacy API that delegates position math to ``packages.fill_accounting``."""
    positions: dict[str, PositionState] = field(default_factory=dict)

    def apply(self, fill: BrokerConfirmedFill) -> PositionState:
        fill.validate()
        current = self.positions.get(fill.instrument, PositionState(fill.instrument))
        canonical_current = CanonicalPosition(
            instrument=current.instrument,
            net_quantity=current.net_quantity,
            average_price=current.average_price if current.net_quantity != 0 else None,
            realized_pnl=current.realized_pnl,
        )
        updated = apply_fill(canonical_current, fill._canonical())
        legacy = _to_legacy(updated)
        self.positions[fill.instrument] = legacy
        return legacy


@dataclass
class ConfirmedFillProcessor:
    """Legacy processor backed by the canonical deterministic accounting engine."""
    ledger: AppendOnlyLedger
    positions: PositionBook = field(default_factory=PositionBook)
    seen_fill_ids: set[str] = field(default_factory=set)
    _fills: dict[str, CanonicalFill] = field(default_factory=dict, repr=False)

    def process(self, fill: BrokerConfirmedFill) -> FillAccountResult:
        fill.validate()
        canonical = fill._canonical()
        existing = self._fills.get(fill.fill_id)
        if existing is not None:
            if existing.fingerprint != canonical.fingerprint:
                raise ValueError(f"fill_id_conflict:{fill.fill_id}")
            current = self.positions.positions[fill.instrument]
            return FillAccountResult(None, True, current)

        event = self.ledger.append(
            event_id=f"FILL:{fill.fill_id}",
            event_type="BROKER_CONFIRMED_FILL",
            correlation_id=fill.client_order_id,
            payload=canonical.canonical_payload(),
            occurred_at=fill.occurred_at,
        )
        self._fills[fill.fill_id] = canonical
        position = self.positions.apply(fill)
        self.seen_fill_ids.add(fill.fill_id)
        return FillAccountResult(event, False, position)

    def process_many(self, fills: Iterable[BrokerConfirmedFill]) -> list[FillAccountResult]:
        return [self.process(fill) for fill in fills]


def execution_tca(arrival_price: Decimal | None, fills: Iterable[BrokerConfirmedFill]) -> dict[str, Decimal | None]:
    """Compatibility wrapper for the canonical fill set; unavailable reference stays UNKNOWN."""
    confirmed = list(fills)
    if not confirmed:
        return {"filled_quantity": Decimal("0"), "execution_vwap": None, "slippage_price": None}
    for fill in confirmed:
        fill.validate()
    total_qty = sum((fill.quantity for fill in confirmed), Decimal("0"))
    vwap = sum((fill.quantity * fill.price for fill in confirmed), Decimal("0")) / total_qty
    slippage = None
    if arrival_price is not None:
        side = confirmed[0].side.upper()
        slippage = (vwap - arrival_price) * (Decimal("1") if side == "BUY" else Decimal("-1"))
    return {"filled_quantity": total_qty, "execution_vwap": vwap, "slippage_price": slippage}


__all__ = ["BrokerConfirmedFill", "ConfirmedFillProcessor", "FillAccountResult", "PositionBook", "PositionState", "execution_tca"]
