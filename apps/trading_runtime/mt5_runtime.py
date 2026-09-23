"""Read-only MT5 runtime adapter for quotes and broker instrument contracts."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from apps.execution_gateway.mt5_gateway import DemoOnlyMT5Gateway
from apps.execution_gateway.mt5_market_data import MT5MarketDataAdapter
from packages.models import InstrumentSpec, Quote


class MT5RuntimeAdapter:
    """Expose verified MT5 market-data and contract facts."""

    def __init__(self, gateway: DemoOnlyMT5Gateway) -> None:
        self.gateway = gateway
        self.market_data = MT5MarketDataAdapter(gateway.mt5_api())

    def quote(self, symbol: str, *, now_ms: int) -> Quote:
        symbol = symbol.strip()
        if not symbol:
            raise ValueError("symbol is required")
        if now_ms <= 0:
            raise ValueError("now_ms must be positive")
        tick = self.gateway.mt5_api().symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError(f"symbol_info_tick unavailable:{symbol}")
        bid = Decimal(str(getattr(tick, "bid", 0)))
        ask = Decimal(str(getattr(tick, "ask", 0)))
        event_time_ms = int(getattr(tick, "time_msc", 0) or 0)
        if event_time_ms <= 0:
            event_time_ms = int(getattr(tick, "time", 0) or 0) * 1000
        if bid <= 0 or ask <= 0 or ask < bid or event_time_ms <= 0:
            raise RuntimeError(f"invalid broker quote:{symbol}")
        return Quote(symbol, bid, ask, event_time_ms, "hfm_mt5")

    def instrument_spec(self, symbol: str) -> InstrumentSpec:
        symbol = symbol.strip()
        info = self.gateway.mt5_api().symbol_info(symbol)
        if info is None:
            raise RuntimeError(f"symbol_info unavailable:{symbol}")

        def d(name: str) -> Decimal:
            value = getattr(info, name, None)
            if value is None or Decimal(str(value)) <= 0:
                raise RuntimeError(f"missing broker contract field:{symbol}:{name}")
            return Decimal(str(value))

        return InstrumentSpec(
            symbol=symbol,
            base_ccy=str(getattr(info, "currency_base", "") or ""),
            quote_ccy=str(getattr(info, "currency_profit", "") or ""),
            contract_size=d("trade_contract_size"),
            point=d("point"),
            tick_size=d("trade_tick_size"),
            tick_value=d("trade_tick_value"),
            min_volume=d("volume_min"),
            max_volume=d("volume_max"),
            volume_step=d("volume_step"),
        )

    def completed_bars(self, *, symbol: str, timeframe: str, count: int = 500):
        return list(self.market_data.fetch_completed_bars(symbol=symbol, timeframe=timeframe, count=count))


__all__ = ["MT5RuntimeAdapter"]
