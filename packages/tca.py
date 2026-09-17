"""Deterministic transaction-cost analysis primitives.

TCA is computed only from observed execution and market-reference inputs. Missing
quotes or markouts remain UNKNOWN; this module never reconstructs a market price
from the fill itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from .fill_accounting import BrokerConfirmedFill

Side = Literal["BUY", "SELL"]


def _d(value: Decimal | str | int | float) -> Decimal:
    value = value if isinstance(value, Decimal) else Decimal(str(value))
    if not value.is_finite():
        raise ValueError("decimal value must be finite")
    return value


@dataclass(frozen=True)
class ReferenceQuote:
    bid: Decimal
    ask: Decimal
    captured_at: str

    def __post_init__(self) -> None:
        bid, ask = _d(self.bid), _d(self.ask)
        if bid <= 0 or ask <= 0 or ask < bid:
            raise ValueError("quote must satisfy 0 < bid <= ask")
        if not self.captured_at.strip():
            raise ValueError("captured_at must be non-empty")
        object.__setattr__(self, "bid", bid)
        object.__setattr__(self, "ask", ask)

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / Decimal("2")

    @property
    def spread(self) -> Decimal:
        return self.ask - self.bid


@dataclass(frozen=True)
class MarkoutObservation:
    horizon: str
    mid: Decimal
    observed_at: str

    def __post_init__(self) -> None:
        mid = _d(self.mid)
        if mid <= 0:
            raise ValueError("markout mid must be > 0")
        if not self.horizon.strip() or not self.observed_at.strip():
            raise ValueError("horizon and observed_at must be non-empty")
        object.__setattr__(self, "mid", mid)


@dataclass(frozen=True)
class TCAResult:
    instrument: str
    side: Side
    requested_quantity: Decimal
    executed_quantity: Decimal
    execution_vwap: Decimal | None
    arrival_mid: Decimal | None
    arrival_spread: Decimal | None
    signed_slippage_price: Decimal | None
    signed_slippage_bps: Decimal | None
    markouts_bps: tuple[tuple[str, Decimal], ...]
    status: str


def _side_sign(side: str) -> Decimal:
    return Decimal("1") if side == "BUY" else Decimal("-1")


def analyze_tca(
    *,
    fills: tuple[BrokerConfirmedFill, ...],
    requested_quantity: Decimal | str | int,
    arrival_quote: ReferenceQuote | None,
    markouts: tuple[MarkoutObservation, ...] = (),
) -> TCAResult:
    if not fills:
        raise ValueError("at least one confirmed fill is required")
    instrument = fills[0].instrument
    side = fills[0].side
    if any(fill.instrument != instrument or fill.side != side for fill in fills):
        raise ValueError("TCA fill set must contain one instrument and one side")
    requested = _d(requested_quantity)
    if requested <= 0:
        raise ValueError("requested_quantity must be > 0")
    executed = sum((fill.quantity for fill in fills), Decimal("0"))
    if executed <= 0 or executed > requested:
        raise ValueError("executed quantity must be > 0 and <= requested quantity")

    vwap = sum((fill.quantity * fill.price for fill in fills), Decimal("0")) / executed
    if arrival_quote is None:
        return TCAResult(
            instrument, side, requested, executed, vwap, None, None, None, None, (), "UNKNOWN_ARRIVAL_QUOTE"
        )

    arrival_mid = arrival_quote.mid
    signed_price = _side_sign(side) * (vwap - arrival_mid)
    signed_bps = (signed_price / arrival_mid) * Decimal("10000")

    markout_values: list[tuple[str, Decimal]] = []
    for observation in sorted(markouts, key=lambda value: (value.horizon, value.observed_at)):
        # Positive markout means the market moved favorably after execution.
        favorable_price = _side_sign(side) * (observation.mid - vwap)
        favorable_bps = (favorable_price / vwap) * Decimal("10000")
        markout_values.append((observation.horizon, favorable_bps))

    return TCAResult(
        instrument, side, requested, executed, vwap, arrival_mid, arrival_quote.spread,
        signed_price, signed_bps, tuple(markout_values), "OK"
    )


__all__ = ["MarkoutObservation", "ReferenceQuote", "TCAResult", "analyze_tca"]
