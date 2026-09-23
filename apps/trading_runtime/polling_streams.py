"""Bounded polling streams for MT5-style APIs without pretending polling is streaming."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from packages.event_bus import EventBus
from packages.events import MarketQuoteEvent


@dataclass
class QuotePollingStream:
    feed: object
    symbols: tuple[str, ...]
    event_bus: EventBus
    source_version: str = "mt5-poll-v1"
    last_event_time_ms: dict[str, int] | None = None

    def __post_init__(self) -> None:
        self.symbols = tuple(dict.fromkeys(s.strip().upper() for s in self.symbols if s.strip()))
        if not self.symbols:
            raise ValueError("quote polling stream requires symbols")
        if self.last_event_time_ms is None:
            self.last_event_time_ms = {}

    def poll_once(self, *, now_ms: int) -> tuple[object, ...]:
        if now_ms <= 0:
            raise ValueError("now_ms must be positive")
        emitted: list[object] = []
        assert self.last_event_time_ms is not None
        for symbol in self.symbols:
            quote = self.feed.quote(symbol, now_ms=now_ms)
            if quote.event_time_ms > now_ms:
                raise RuntimeError(f"future quote from broker:{symbol}")
            previous = self.last_event_time_ms.get(symbol, 0)
            if quote.event_time_ms <= previous:
                continue
            self.last_event_time_ms[symbol] = quote.event_time_ms
            event = MarketQuoteEvent(
                event_id=f"quote:{symbol}:{quote.event_time_ms}",
                occurred_at_ms=now_ms,
                source="quote_polling_stream",
                source_version=self.source_version,
                symbol=symbol,
                bid=str(quote.bid),
                ask=str(quote.ask),
                event_time_ms=quote.event_time_ms,
                usable_at_ms=quote.event_time_ms,
            )
            self.event_bus.publish(event)
            emitted.append(event)
        return tuple(emitted)


__all__ = ["QuotePollingStream"]
