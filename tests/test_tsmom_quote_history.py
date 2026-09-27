from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from apps.execution_gateway.mt5_quote_history import MT5QuoteHistoryAdapter, RollingDailyQuoteCache


class FakeTicks:
    COPY_TICKS_INFO = 2

    def __init__(self):
        self.calls = []

    def symbol_info(self, symbol):
        return type("Info", (), {"visible": True})()

    def symbol_select(self, symbol, enabled):
        return True

    def copy_ticks_range(self, symbol, start, end, flags):
        self.calls.append((symbol, start, end, flags))
        return [
            {"time_msc": 1_700_000_000_000, "bid": 150.10, "ask": 150.12},
            {"time_msc": 1_700_000_001_000, "bid": 150.11, "ask": 150.13},
        ]

    def last_error(self):
        return (0, "OK")


def test_quote_adapter_reads_bid_ask_ticks():
    mt5 = FakeTicks()
    adapter = MT5QuoteHistoryAdapter(mt5)
    quotes = adapter.fetch_quotes_range(
        symbol="USDJPY",
        start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end=datetime(2026, 1, 1, 1, tzinfo=timezone.utc),
    )
    assert len(quotes) == 2
    assert quotes[0].bid == Decimal("150.1")
    assert quotes[0].ask == Decimal("150.12")
    assert quotes[0].spread == Decimal("0.02")
    assert quotes[0].mid == Decimal("150.11")
    assert mt5.calls[0][3] == mt5.COPY_TICKS_INFO


def test_quote_adapter_rejects_naive_datetimes():
    adapter = MT5QuoteHistoryAdapter(FakeTicks())
    with pytest.raises(ValueError, match="timezone-aware"):
        adapter.fetch_quotes_range(
            symbol="USDJPY",
            start=datetime(2026, 1, 1),
            end=datetime(2026, 1, 1, 1, tzinfo=timezone.utc),
        )


def test_daily_cache_uses_bounded_storage():
    cache = RollingDailyQuoteCache(MT5QuoteHistoryAdapter(FakeTicks()), max_days=2)
    # MetaTrader 5 Python API timestamps are already UTC epoch values.
    normalized_first = 1_700_000_000_000
    target = normalized_first + 500
    quote = cache.quote_at_or_before(symbol="USDJPY", event_time_ms=target, max_gap_ms=5_000)
    assert quote is not None
    assert quote.event_time_ms == normalized_first
    assert len(cache._cache) <= 2


def test_quote_at_or_before_never_returns_future_quote():
    cache = RollingDailyQuoteCache(MT5QuoteHistoryAdapter(FakeTicks()), max_days=2)
    normalized_first = 1_700_000_000_000
    target = normalized_first - 500
    quote = cache.quote_at_or_before(symbol="USDJPY", event_time_ms=target, max_gap_ms=5_000)
    assert quote is None
