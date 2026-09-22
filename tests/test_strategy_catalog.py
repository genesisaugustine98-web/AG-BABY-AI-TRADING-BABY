from packages.strategy_catalog import default_slate


def test_default_slate_uses_requested_evaluation_window_and_warmup():
    slate = default_slate()
    assert slate.window.evaluation_start == "2015-01-01"
    assert slate.window.evaluation_end == "2025-12-31"
    assert slate.window.warmup_start == "2014-01-01"
    assert slate.live_promotion == "disabled"


def test_default_slate_has_cross_asset_core_hypotheses():
    slate = default_slate()
    ids = {strategy.strategy_id for strategy in slate.strategies}
    assert {
        "cross_asset_tsmom",
        "cross_sectional_momentum",
        "multiasset_carry",
        "cross_asset_value",
        "defensive_low_risk",
        "short_horizon_mean_reversion",
        "volatility_targeting_overlay",
        "regime_risk_overlay",
    } <= ids


def test_universe_covers_broad_multi_asset_scope():
    slate = default_slate()
    for bucket in ("fx", "equity_indices", "rates", "commodities"):
        assert len(slate.asset_universe[bucket]) >= 4
