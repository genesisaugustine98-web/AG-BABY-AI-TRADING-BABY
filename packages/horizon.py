"""Native strategy horizons and timeframe utilities.

A timeframe is not a strategy. Each alpha engine should operate on the clock on which
its information decays, while the portfolio layer remains time-horizon agnostic.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Timeframe(str, Enum):
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"
    W1 = "W1"


_SECONDS = {
    Timeframe.M1: 60,
    Timeframe.M5: 300,
    Timeframe.M15: 900,
    Timeframe.M30: 1800,
    Timeframe.H1: 3600,
    Timeframe.H4: 14400,
    Timeframe.D1: 86400,
    Timeframe.W1: 604800,
}


@dataclass(frozen=True)
class HorizonSpec:
    name: str
    timeframe: Timeframe
    horizon_seconds: int
    lookback_bars: int
    execution_timeframe: Timeframe
    max_signal_age_seconds: int

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("horizon name is required")
        if self.lookback_bars < 2:
            raise ValueError("lookback_bars must be >= 2")
        if self.max_signal_age_seconds < self.horizon_seconds:
            raise ValueError("max_signal_age_seconds must cover one full horizon")


def timeframe_seconds(timeframe: str | Timeframe) -> int:
    tf = timeframe if isinstance(timeframe, Timeframe) else Timeframe(str(timeframe).upper())
    return _SECONDS[tf]


def bars_to_seconds(timeframe: str | Timeframe, bars: int) -> int:
    if bars < 1:
        raise ValueError("bars must be >= 1")
    return timeframe_seconds(timeframe) * bars


def default_horizon_plan() -> tuple[HorizonSpec, ...]:
    """Conservative research defaults; these are candidates, not production truths."""
    return (
        HorizonSpec("strategic", Timeframe.D1, 86400, 252, Timeframe.H4, 172800),
        HorizonSpec("swing", Timeframe.H4, 14400, 126, Timeframe.M15, 28800),
        HorizonSpec("tactical", Timeframe.H1, 3600, 120, Timeframe.M5, 7200),
        HorizonSpec("intraday_setup", Timeframe.M15, 900, 96, Timeframe.M5, 1800),
        HorizonSpec("execution", Timeframe.M5, 300, 24, Timeframe.M1, 600),
    )


def native_horizon_ok(*, signal_horizon_seconds: int, execution_seconds: int) -> bool:
    """Reject systems whose execution latency is too large for their signal half-life."""
    if signal_horizon_seconds < 1 or execution_seconds < 0:
        raise ValueError("invalid horizon values")
    return execution_seconds < signal_horizon_seconds


__all__ = ["Timeframe", "HorizonSpec", "timeframe_seconds", "bars_to_seconds", "default_horizon_plan", "native_horizon_ok"]
