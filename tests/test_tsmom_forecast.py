from dataclasses import replace
from decimal import Decimal

import pytest

from apps.execution_gateway.mt5_market_data import MT5MarketDataAdapter
from packages.tsmom_forecast import PriceBar, TSMOMForecastModel, dataset_fingerprint


def bars(n=180):
    rows = []
    for i in range(n):
        close = Decimal("100") + Decimal(i) * Decimal("0.10")
        rows.append(
            PriceBar(
                symbol="USDJPY",
                event_time_ms=(i + 1) * 3_600_000,
                usable_at_ms=(i + 1) * 3_600_000,
                close=close,
                source="test",
                source_version="v1",
                observation_id=f"bar-{i+1}",
            )
        )
    return rows


def test_dataset_fingerprint_is_deterministic():
    rows = bars()
    assert dataset_fingerprint(rows) == dataset_fingerprint(list(reversed(rows)))


def test_tsmom_fit_produces_validation_metadata():
    model = TSMOMForecastModel(
        lookback_bars=12,
        horizon_bars=3,
        min_training_samples=30,
        bar_interval_seconds=3600,
    )
    result = model.fit(
        bars(),
        dataset_fingerprint="dataset-1",
        code_commit_sha="abc123",
    )
    assert result.development_n >= 30
    assert result.validation_n >= 30
    assert result.holdout_n >= 30
    assert result.calibration_score >= Decimal("0.65")
    assert result.validation_status == "candidate"
    assert result.calibration_gate == "passed"


def test_tsmom_prediction_is_point_in_time():
    rows = bars()
    model = TSMOMForecastModel(lookback_bars=12, horizon_bars=3, min_training_samples=30)
    model.fit(rows, dataset_fingerprint="dataset-1", code_commit_sha="abc123")

    decision_time = rows[120].event_time_ms
    forecast = model.predict(rows, decision_time_ms=decision_time)
    indexed = model.predict_at_index(rows, decision_index=120)

    assert forecast.model_id == "tsmom-fixed-v1"
    assert forecast.version == "1"
    assert forecast.expected_return > 0
    assert forecast.probability_up > Decimal("0.5")
    assert forecast.generated_at_ms == rows[120].usable_at_ms
    assert "bar-121" in forecast.evidence_ids
    assert "bar-122" not in forecast.evidence_ids
    assert indexed.expected_return == forecast.expected_return
    assert indexed.probability_up == forecast.probability_up
    assert indexed.generated_at_ms == rows[120].usable_at_ms


def test_tsmom_requires_enough_training_data():
    model = TSMOMForecastModel(lookback_bars=12, horizon_bars=3, min_training_samples=30)
    with pytest.raises(ValueError, match="insufficient bars"):
        model.fit(
            bars(50),
            dataset_fingerprint="dataset-1",
            code_commit_sha="abc123",
        )


class FakeMT5:
    TIMEFRAME_H1 = 16385

    def symbol_info(self, symbol):
        return type("Info", (), {"visible": True})()

    def symbol_select(self, symbol, enabled):
        return True

    def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
        return [
            {"time": 1_000 + i * 3600, "close": 100.0 + i}
            for i in range(count)
        ]

    def last_error(self):
        return (0, "OK")


def test_mt5_market_data_excludes_forming_bar_and_normalizes_time():
    adapter = MT5MarketDataAdapter(FakeMT5())
    rows = adapter.fetch_completed_bars(symbol="USDJPY", timeframe="H1", count=5)
    assert len(rows) == 5
    assert rows[0].source == "hfm_mt5"
    assert rows[0].observation_id.startswith("mt5:USDJPY:H1:")
    assert rows[0].event_time_ms < rows[-1].event_time_ms
    assert all(row.usable_at_ms == row.event_time_ms + 3600 * 1000 for row in rows)


def test_mt5_market_data_rejects_unsupported_timeframe():
    with pytest.raises(ValueError, match="unsupported timeframe"):
        MT5MarketDataAdapter(FakeMT5()).fetch_completed_bars(
            symbol="USDJPY", timeframe="M2", count=5
        )


def test_tsmom_training_targets_do_not_cross_split_boundary():
    rows = bars(240)
    samples = TSMOMForecastModel._samples(
        rows, 12, 120, 12, 6
    )
    assert samples
    assert max(index + 6 for _, _, index, _ in samples) < 120



def test_tsmom_prediction_at_index_uses_bar_availability_time():
    base = bars(180)
    rows = [replace(row, usable_at_ms=row.event_time_ms + 3_600_000) for row in base]
    model = TSMOMForecastModel(lookback_bars=12, horizon_bars=3, min_training_samples=30)
    model.fit(rows, dataset_fingerprint="dataset-1", code_commit_sha="abc123")
    forecast = model.predict_at_index(rows, decision_index=120)
    assert forecast.generated_at_ms == rows[120].usable_at_ms
