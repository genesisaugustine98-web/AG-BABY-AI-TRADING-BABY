from apps.research.free_stack_adapter import FreeStackResearchAdapter, _binance_observation
from apps.research.free_stack_sources import SourceSnapshot


def test_binance_snapshot_becomes_research_observation():
    snap = SourceSnapshot(
        "binance",
        "https://api.binance.com/api/v3/ticker/bookTicker",
        1_700_000_000_000,
        "abc123",
        {"symbol": "BTCUSDT", "bidPrice": "100", "askPrice": "101"},
    )
    obs = _binance_observation(snap, "BTCUSDT")
    assert obs.instrument == "BTCUSDT"
    assert obs.close == 100.5
    assert obs.source
    assert obs.observation_id.startswith("binance:")


def test_adapter_constructs():
    assert FreeStackResearchAdapter() is not None
