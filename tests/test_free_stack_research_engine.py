from decimal import Decimal

from apps.research.free_stack_research_engine import binance_klines_to_price_bars
from packages.horizon import Timeframe


def test_closed_kline_normalization_preserves_close_time_boundary():
    rows = [
        [0, "99", "101", "98", "100", "1", 3599999],
        [3600000, "100", "102", "99", "101", "1", 7199999],
    ]
    bars = binance_klines_to_price_bars(rows, symbol="BTCUSDT", timeframe=Timeframe.H1)
    assert len(bars) == 2
    assert bars[0].event_time_ms == 3599999
    assert bars[0].usable_at_ms == 3599999
    assert bars[1].close == Decimal("101")


def test_kline_observation_is_provenance_bound():
    rows = [[3600000, "100", "102", "99", "101", "1", 7199999]]
    bar = binance_klines_to_price_bars(rows, symbol="BTCUSDT", timeframe=Timeframe.H1)[0]
    assert bar.source == "binance_public_klines"
    assert bar.observation_id.startswith("binance:kline:")
