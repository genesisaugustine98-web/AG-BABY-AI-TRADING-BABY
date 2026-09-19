"""Read-only HFM/MT5 historical bid/ask quote access for research replay.

This adapter reads real historical Bid/Ask-information ticks from MetaTrader 5 using
COPY_TICKS_INFO. It never submits, modifies, or cancels orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

from .mt5_time import broker_server_epoch_ms_to_utc_ms


@dataclass(frozen=True)
class HistoricalQuote:
    event_time_ms: int
    bid: Decimal
    ask: Decimal
    source: str = "hfm_mt5_ticks"
    source_version: str = "mt5-copy-ticks-info"

    def validate(self) -> None:
        if self.event_time_ms <= 0:
            raise ValueError("quote timestamp must be positive")
        if self.bid <= 0 or self.ask <= 0:
            raise ValueError("quote prices must be positive")
        if self.ask < self.bid:
            raise ValueError("quote cannot be crossed")
        if not self.source.strip() or not self.source_version.strip():
            raise ValueError("quote provenance is required")

    @property
    def spread(self) -> Decimal:
        return self.ask - self.bid

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / Decimal("2")


class MT5QuoteHistoryAdapter:
    """Fetch historical Bid/Ask-change ticks from an already-verified MT5 session."""

    def __init__(self, mt5_api: Any):
        self.mt5 = mt5_api

    def fetch_quotes_range(
        self,
        *,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> tuple[HistoricalQuote, ...]:
        symbol = symbol.strip()
        if not symbol:
            raise ValueError("symbol is required")
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start and end must be timezone-aware")
        start_utc = start.astimezone(timezone.utc)
        end_utc = end.astimezone(timezone.utc)
        if end_utc <= start_utc:
            raise ValueError("end must be after start")

        info = self.mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError(f"symbol_info unavailable:{symbol}")
        if getattr(info, "visible", True) is False:
            if self.mt5.symbol_select(symbol, True) is False:
                raise RuntimeError(f"symbol_select failed:{symbol}")

        flags = getattr(self.mt5, "COPY_TICKS_INFO")
        ticks = self.mt5.copy_ticks_range(symbol, start_utc, end_utc, flags)
        if ticks is None:
            raise RuntimeError(
                f"copy_ticks_range failed:{symbol}:{start_utc.isoformat()}:{end_utc.isoformat()}:"
                f"{self.mt5.last_error()}"
            )

        quotes: list[HistoricalQuote] = []
        for row in ticks:
            dtype = getattr(row, "dtype", None)
            names = getattr(dtype, "names", None)
            raw_time_msc = row["time_msc"] if names and "time_msc" in names else row["time"] * 1000
            try:
                event_time_ms = broker_server_epoch_ms_to_utc_ms(int(raw_time_msc))
                bid = Decimal(str(row["bid"]))
                ask = Decimal(str(row["ask"]))
            except (KeyError, TypeError, ValueError, OverflowError, RuntimeError) as exc:
                raise ValueError("malformed historical quote tick") from exc
            if bid <= 0 or ask <= 0:
                continue
            quote = HistoricalQuote(event_time_ms, bid, ask)
            quote.validate()
            quotes.append(quote)

        quotes.sort(key=lambda quote: quote.event_time_ms)
        return tuple(quotes)

    def fetch_utc_day(self, *, symbol: str, day: date) -> tuple[HistoricalQuote, ...]:
        start = datetime.combine(day, time.min, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        return self.fetch_quotes_range(symbol=symbol, start=start, end=end)


class RollingDailyQuoteCache:
    """Small bounded cache so multi-year replay does not retain every tick in memory."""

    def __init__(self, adapter: MT5QuoteHistoryAdapter, *, max_days: int = 2):
        if max_days < 1:
            raise ValueError("max_days must be >= 1")
        self.adapter = adapter
        self.max_days = max_days
        self._cache: dict[tuple[str, date], tuple[HistoricalQuote, ...]] = {}

    def _load(self, symbol: str, day: date) -> tuple[HistoricalQuote, ...]:
        key = (symbol, day)
        if key not in self._cache:
            self._cache[key] = self.adapter.fetch_utc_day(symbol=symbol, day=day)
            while len(self._cache) > self.max_days:
                self._cache.pop(next(iter(self._cache)))
        return self._cache[key]

    def quote_at_or_after(
        self,
        *,
        symbol: str,
        event_time_ms: int,
        max_gap_ms: int,
    ) -> HistoricalQuote | None:
        if event_time_ms <= 0:
            raise ValueError("event_time_ms must be positive")
        if max_gap_ms < 0:
            raise ValueError("max_gap_ms must be >= 0")
        target = datetime.fromtimestamp(event_time_ms / 1000, tz=timezone.utc)
        day = target.date()
        for candidate_day in (day, day + timedelta(days=1)):
            quotes = self._load(symbol, candidate_day)
            for quote in quotes:
                if quote.event_time_ms < event_time_ms:
                    continue
                if quote.event_time_ms - event_time_ms <= max_gap_ms:
                    return quote
                break
        return None


__all__ = ["HistoricalQuote", "MT5QuoteHistoryAdapter", "RollingDailyQuoteCache"]
