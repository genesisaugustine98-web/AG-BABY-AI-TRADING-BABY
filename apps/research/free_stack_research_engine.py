"""Connect free/public candles to the existing evidence-first forecast engine.

This is a research adapter only. It produces forecasts/proposals and never creates
TradeIntent objects or calls an execution sink.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from packages.horizon import Timeframe, timeframe_seconds
from packages.multihorizon_decision import HorizonProposal, make_proposal
from packages.tsmom_forecast import PriceBar, TSMOMForecastModel, dataset_fingerprint


_BINANCE_INTERVALS = {
    Timeframe.M5: "5m",
    Timeframe.M15: "15m",
    Timeframe.H1: "1h",
    Timeframe.H4: "4h",
    Timeframe.D1: "1d",
}


@dataclass(frozen=True)
class HorizonForecast:
    timeframe: Timeframe
    model: TSMOMForecastModel
    forecast: object


@dataclass(frozen=True)
class ResearchSnapshot:
    symbol: str
    forecasts: tuple[HorizonForecast, ...]
    proposal: HorizonProposal
    dataset_fingerprints: tuple[tuple[str, str], ...]


def binance_klines_to_price_bars(
    rows: Iterable[list[object] | tuple[object, ...]],
    *,
    symbol: str,
    timeframe: Timeframe,
    source_version: str = "binance-api-v3-klines",
) -> list[PriceBar]:
    """Normalize closed Binance klines into AG-BABY PriceBar records.

    Binance kline timestamps are exchange event times. A completed candle is only
    usable at its close timestamp, preventing the current candle from leaking into
    a retrospective research decision.
    """
    interval_ms = timeframe_seconds(timeframe) * 1000
    bars: list[PriceBar] = []
    for row in rows:
        if len(row) < 7:
            continue
        try:
            open_ms = int(row[0])
            close_ms = int(row[6])
            if close_ms <= 0 or open_ms <= 0:
                continue
            # Drop an incomplete candle. A fully closed interval has its close
            # timestamp within approximately one interval of its opening timestamp.
            if close_ms < open_ms or close_ms - open_ms > interval_ms:
                continue
            close = Decimal(str(row[4]))
            if close <= 0:
                continue
        except (TypeError, ValueError):
            continue
        event_ms = close_ms
        bars.append(
            PriceBar(
                symbol=symbol.strip().upper(),
                event_time_ms=event_ms,
                usable_at_ms=event_ms,
                close=close,
                source="binance_public_klines",
                source_version=source_version,
                observation_id=f"binance:kline:{symbol.upper()}:{timeframe.value}:{open_ms}:{close_ms}",
            )
        )
    bars.sort(key=lambda x: (x.event_time_ms, x.observation_id))
    deduped: list[PriceBar] = []
    seen: set[tuple[int, str]] = set()
    for bar in bars:
        key = (bar.event_time_ms, bar.observation_id)
        if key not in seen:
            seen.add(key)
            deduped.append(bar)
    if any(deduped[i].event_time_ms <= deduped[i - 1].event_time_ms for i in range(1, len(deduped))):
        raise ValueError("normalized bars are not strictly chronological")
    return deduped


class FreeStackResearchEngine:
    """Run the repository TSMOM engine on public candles at native time horizons."""

    def __init__(
        self,
        *,
        client,
        lookback_bars: int = 24,
        min_training_samples: int = 30,
        limit: int = 1000,
    ) -> None:
        if lookback_bars < 2 or min_training_samples < 10:
            raise ValueError("invalid model configuration")
        if not 100 <= limit <= 1000:
            raise ValueError("limit must be between 100 and 1000")
        self.client = client
        self.lookback_bars = lookback_bars
        self.min_training_samples = min_training_samples
        self.limit = limit

    def analyze(
        self,
        *,
        symbol: str,
        timeframes: tuple[Timeframe, ...] = (Timeframe.H1, Timeframe.H4, Timeframe.D1),
        execution_latency_seconds: int = 5,
    ) -> ResearchSnapshot:
        results: list[HorizonForecast] = []
        fingerprints: list[tuple[str, str]] = []
        scores: dict[Timeframe, Decimal] = {}
        for timeframe in timeframes:
            interval = _BINANCE_INTERVALS[timeframe]
            snapshot = self.client.klines(symbol, interval=interval, limit=self.limit)
            bars = binance_klines_to_price_bars(
                snapshot.payload,
                symbol=symbol,
                timeframe=timeframe,
            )
            if len(bars) < max(self.min_training_samples * 3 + self.lookback_bars, 100):
                continue
            model = TSMOMForecastModel(
                lookback_bars=self.lookback_bars,
                horizon_bars=1,
                min_training_samples=self.min_training_samples,
                bar_interval_seconds=timeframe_seconds(timeframe),
            )
            validation = model.fit(
                bars,
                dataset_fingerprint=dataset_fingerprint(bars),
                code_commit_sha="free-stack-runtime",
            )
            forecast = model.predict(bars, decision_time_ms=bars[-1].usable_at_ms)
            results.append(HorizonForecast(timeframe, model, forecast))
            fingerprints.append((timeframe.value, validation.dataset_fingerprint))
            scores[timeframe] = max(
                Decimal("-1"),
                min(Decimal("1"), forecast.expected_return * Decimal("100")),
            )

        if not results:
            raise RuntimeError(f"no horizon has enough public candle history:{symbol}")

        primary = results[0].forecast
        proposal = make_proposal(
            forecasts=scores,
            expected_hold_seconds=primary.horizon_seconds,
            execution_latency_seconds=execution_latency_seconds,
        )
        return ResearchSnapshot(
            symbol=symbol.strip().upper(),
            forecasts=tuple(results),
            proposal=proposal,
            dataset_fingerprints=tuple(fingerprints),
        )


__all__ = [
    "HorizonForecast",
    "ResearchSnapshot",
    "FreeStackResearchEngine",
    "binance_klines_to_price_bars",
]
