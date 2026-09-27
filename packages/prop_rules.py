"""Generic funded-account/contest rule adapter.

Provider rules must be supplied explicitly and refreshed from the provider's current
rulebook. This module never invents a provider's constraints.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PropRuleSet:
    name: str
    daily_loss_limit: Decimal
    max_loss_limit: Decimal
    max_open_positions: int
    min_trading_days: int = 0
    max_holding_seconds: int | None = None
    overnight_allowed: bool = True
    weekend_allowed: bool = True
    ea_allowed: bool = True

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("rule set name is required")
        if not (Decimal("0") < self.daily_loss_limit <= Decimal("1")):
            raise ValueError("daily_loss_limit must be in (0,1]")
        if not (Decimal("0") < self.max_loss_limit <= Decimal("1")):
            raise ValueError("max_loss_limit must be in (0,1]")
        if self.max_open_positions < 1 or self.min_trading_days < 0:
            raise ValueError("position/day limits are invalid")
        if self.max_holding_seconds is not None and self.max_holding_seconds < 1:
            raise ValueError("max_holding_seconds must be positive")


@dataclass(frozen=True)
class PropAccountState:
    equity: Decimal
    start_of_day_equity: Decimal
    high_watermark_equity: Decimal
    open_positions: int
    trading_days_completed: int
    utc_hour: int
    is_weekend: bool

    def __post_init__(self) -> None:
        if self.equity <= 0 or self.start_of_day_equity <= 0 or self.high_watermark_equity <= 0:
            raise ValueError("equity values must be positive")
        if not 0 <= self.utc_hour <= 23:
            raise ValueError("utc_hour must be in [0,23]")
        if self.open_positions < 0 or self.trading_days_completed < 0:
            raise ValueError("state counters cannot be negative")


@dataclass(frozen=True)
class PropCheck:
    allowed: bool
    reasons: tuple[str, ...]


def check_entry(
    *,
    rules: PropRuleSet,
    state: PropAccountState,
    additional_risk_fraction: Decimal,
    expected_hold_seconds: int,
    opens_new_position: bool,
) -> PropCheck:
    """Apply account-level constraints before a strategy-level risk decision."""
    reasons: list[str] = []
    if additional_risk_fraction < 0:
        reasons.append("NEGATIVE_RISK")
    if opens_new_position and state.open_positions >= rules.max_open_positions:
        reasons.append("MAX_OPEN_POSITIONS")
    if not rules.overnight_allowed and expected_hold_seconds > max(0, (24 - state.utc_hour) * 3600):
        reasons.append("OVERNIGHT_RESTRICTED")
    if not rules.weekend_allowed and state.is_weekend:
        reasons.append("WEEKEND_RESTRICTED")
    if rules.max_holding_seconds is not None and expected_hold_seconds > rules.max_holding_seconds:
        reasons.append("HOLDING_LIMIT")
    if not rules.ea_allowed:
        reasons.append("AUTOMATION_NOT_ALLOWED")
    if state.trading_days_completed < 0:
        reasons.append("INVALID_TRADING_DAY_STATE")

    projected_daily_loss = max(Decimal("0"), (state.start_of_day_equity - state.equity) / state.start_of_day_equity)
    if projected_daily_loss + additional_risk_fraction >= rules.daily_loss_limit:
        reasons.append("DAILY_LOSS_BUFFER_INSUFFICIENT")

    projected_total_loss = max(Decimal("0"), (state.high_watermark_equity - state.equity) / state.high_watermark_equity)
    if projected_total_loss + additional_risk_fraction >= rules.max_loss_limit:
        reasons.append("MAX_LOSS_BUFFER_INSUFFICIENT")

    return PropCheck(not reasons, tuple(reasons))


__all__ = ["PropRuleSet", "PropAccountState", "PropCheck", "check_entry"]
