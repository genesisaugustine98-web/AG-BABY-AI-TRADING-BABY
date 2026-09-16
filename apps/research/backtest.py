"""Small, deterministic bar replay engine with point-in-time and cost controls."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Iterable

from .cost_model import ExecutionCosts, net_return
from .data_contract import MarketObservation


@dataclass(frozen=True)
class BacktestConfig:
    horizon_bars: int = 1
    delay_bars: int = 0
    costs: ExecutionCosts = ExecutionCosts()

    def validate(self) -> None:
        if self.horizon_bars < 1:
            raise ValueError("horizon_bars must be >= 1")
        if self.delay_bars < 0:
            raise ValueError("delay_bars cannot be negative")
        self.costs.validate()


@dataclass(frozen=True)
class BacktestTrade:
    observation_id: str
    instrument: str
    decision_time: object
    entry_close: Decimal
    exit_close: Decimal
    gross_return: Decimal
    net_return: Decimal


def run_replay(
    observations: Iterable[MarketObservation],
    signal: Callable[[MarketObservation], int],
    config: BacktestConfig,
) -> list[BacktestTrade]:
    """Replay chronologically with an explicit availability boundary.

    The signal is evaluated only on observations available at their decision
    timestamp. An input whose usable_at is later than event_time is therefore
    skipped rather than treated as instantaneous information.
    """
    config.validate()
    bars = sorted(observations, key=lambda item: item.event_time)
    trades: list[BacktestTrade] = []

    for i, obs in enumerate(bars):
        if not obs.usable_for(obs.event_time):
            continue
        direction = signal(obs)
        if direction not in (-1, 0, 1):
            raise ValueError("signal must be -1, 0 or +1")
        entry_idx = i + config.delay_bars
        exit_idx = entry_idx + config.horizon_bars
        if direction == 0 or exit_idx >= len(bars):
            continue
        entry = bars[entry_idx]
        exit_bar = bars[exit_idx]
        if not obs.usable_for(entry.event_time):
            continue
        gross = direction * ((exit_bar.close / entry.close) - Decimal("1"))
        trades.append(
            BacktestTrade(
                observation_id=obs.observation_id,
                instrument=obs.instrument,
                decision_time=obs.event_time,
                entry_close=entry.close,
                exit_close=exit_bar.close,
                gross_return=gross,
                net_return=net_return(gross, config.costs),
            )
        )
    return trades
