"""Read-only MT5 market-data adapter.

Completed bars are fetched with position 1 so the currently forming bar is excluded.
Broker-local MT5 timestamps are normalized through mt5_time.py. This adapter never
submits, modifies, or cancels an order.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from .mt5_time import broker_server_epoch_seconds_to_utc_ms
from packages.tsmom_forecast import PriceBar


TIMEFRAME_NAMES = {
    "M1": "TIMEFRAME_M1",
    "M5": "TIMEFRAME_M5",
    "M15": "TIMEFRAME_M15",
    "M30": "TIMEFRAME_M30",
    "H1": "TIMEFRAME_H1",
    "H4": "TIMEFRAME_H4",
    "D1": "TIMEFRAME_D1",
}


class MT5MarketDataAdapter:
    def __init__(self, mt5_api: Any):
        self.mt5 = mt5_api

    def fetch_completed_bars(
        self,
        *,
        symbol: str,
        timeframe: str = "H1",
        count: int = 1000,
        source_version: str = "mt5-hfm-demo",
    ) -> tuple[PriceBar, ...]:
        symbol = symbol.strip()
        timeframe = timeframe.upper().strip()
        if not symbol:
            raise ValueError("symbol is required")
        if timeframe not in TIMEFRAME_NAMES:
            raise ValueError(f"unsupported timeframe:{timeframe}")
        if count < 3:
            raise ValueError("count must be >= 3")

        info = self.mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError(f"symbol_info unavailable:{symbol}")
        if getattr(info, "visible", True) is False:
            if self.mt5.symbol_select(symbol, True) is False:
                raise RuntimeError(f"symbol_select failed:{symbol}")

        tf = getattr(self.mt5, TIMEFRAME_NAMES[timeframe])
        rates = self.mt5.copy_rates_from_pos(symbol, tf, 1, count)
        if rates is None:
            raise RuntimeError(f"copy_rates_from_pos failed:{symbol}:{timeframe}:{self.mt5.last_error()}")
        if len(rates) < 3:
            raise RuntimeError(f"insufficient completed bars:{symbol}:{timeframe}:{len(rates)}")

        bars: list[PriceBar] = []
        for row in rates:
            event_time_ms = broker_server_epoch_seconds_to_utc_ms(int(row["time"]))
            close = Decimal(str(row["close"]))
            observation_id = f"mt5:{symbol}:{timeframe}:{event_time_ms}"
            bars.append(
                PriceBar(
                    symbol=symbol,
                    event_time_ms=event_time_ms,
                    usable_at_ms=event_time_ms,
                    close=close,
                    source="hfm_mt5",
                    source_version=source_version,
                    observation_id=observation_id,
                )
            )
        bars.sort(key=lambda x: x.event_time_ms)
        return tuple(bars)


__all__ = ["MT5MarketDataAdapter", "TIMEFRAME_NAMES"]
