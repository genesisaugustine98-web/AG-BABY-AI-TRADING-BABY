from decimal import Decimal

from apps.trading_runtime.polling_streams import QuotePollingStream
from packages.event_bus import EventBus
from packages.models import Quote


class Feed:
    def __init__(self):
        self.events = {
            "EURUSD": Quote("EURUSD", Decimal("1.1"), Decimal("1.1001"), 1000, "test")
        }

    def quote(self, symbol, *, now_ms):
        return self.events[symbol]


def test_quote_stream_is_monotonic_and_deduplicates():
    bus = EventBus()
    stream = QuotePollingStream(Feed(), ("EURUSD",), bus)
    assert len(stream.poll_once(now_ms=2000)) == 1
    assert len(stream.poll_once(now_ms=2000)) == 0
    assert len(bus.history()) == 1


def test_quote_stream_rejects_future_broker_timestamp():
    class FutureFeed(Feed):
        def quote(self, symbol, *, now_ms):
            return Quote(symbol, Decimal("1.1"), Decimal("1.1001"), now_ms + 1, "test")

    stream = QuotePollingStream(FutureFeed(), ("EURUSD",), EventBus())
    try:
        stream.poll_once(now_ms=2000)
    except RuntimeError as exc:
        assert "future quote" in str(exc)
    else:
        raise AssertionError("future quote must be rejected")
