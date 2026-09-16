"""Deterministic execution-cost model for research replay.

All rates are fractions of notional unless documented otherwise.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ExecutionCosts:
    spread_fraction: Decimal = Decimal("0")
    slippage_fraction: Decimal = Decimal("0")
    commission_fraction: Decimal = Decimal("0")

    @property
    def total_round_trip_fraction(self) -> Decimal:
        return self.spread_fraction + self.slippage_fraction + self.commission_fraction

    def validate(self) -> None:
        if any(value < 0 for value in (self.spread_fraction, self.slippage_fraction, self.commission_fraction)):
            raise ValueError("cost fractions cannot be negative")


def net_return(gross_return: Decimal, costs: ExecutionCosts) -> Decimal:
    costs.validate()
    return gross_return - costs.total_round_trip_fraction
