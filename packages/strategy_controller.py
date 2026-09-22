"""Strategy-controller boundary.

Controllers produce forecasts and auditable opportunity candidates. They never submit orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from .events import StrategyDecision
from .models import MarketState
from .opportunity import OpportunityCandidate, build_candidate
from .tsmom_forecast import PriceBar, TSMOMForecastModel


class StrategyController(Protocol):
    strategy_id: str
    symbols: tuple[str, ...]

    def evaluate(
        self,
        *,
        symbol: str,
        bars: list[PriceBar],
        market: MarketState,
        decision_time_ms: int,
        estimated_cost: Decimal,
        safety_margin: Decimal,
    ) -> StrategyDecision | None:
        ...


@dataclass
class TSMOMController:
    model: TSMOMForecastModel
    symbols: tuple[str, ...]
    strategy_id: str = "cross_asset_tsmom"

    def __post_init__(self) -> None:
        normalized = tuple(dict.fromkeys(s.strip().upper() for s in self.symbols if s.strip()))
        if not normalized:
            raise ValueError("TSMOM controller requires at least one symbol")
        self.symbols = normalized

    def evaluate(
        self,
        *,
        symbol: str,
        bars: list[PriceBar],
        market: MarketState,
        decision_time_ms: int,
        estimated_cost: Decimal,
        safety_margin: Decimal,
    ) -> StrategyDecision | None:
        if symbol.strip().upper() not in self.symbols:
            raise ValueError(f"symbol not configured for controller:{symbol}")
        forecast = self.model.predict(bars, decision_time_ms=decision_time_ms)
        candidate: OpportunityCandidate = build_candidate(
            instrument=symbol,
            forecast=forecast,
            market=market,
            estimated_cost=estimated_cost,
            safety_margin=safety_margin,
            evidence_ids=tuple(sorted(forecast.evidence_ids)),
        )
        return StrategyDecision(
            strategy_id=self.strategy_id,
            symbol=symbol.strip().upper(),
            forecast=forecast,
            candidate=candidate,
            evidence_ids=forecast.evidence_ids,
        )


__all__ = ["StrategyController", "TSMOMController"]
