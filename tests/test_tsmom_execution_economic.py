from decimal import Decimal

from packages.tsmom_execution_economic import evaluate_split_with_quotes
from packages.tsmom_forecast import TSMOMForecastModel, PriceBar
from apps.execution_gateway.mt5_quote_history import HistoricalQuote
from tests.test_tsmom_forecast import bars


def test_quote_aware_replay_uses_executable_side_of_spread():
    rows = bars(240)
    model = TSMOMForecastModel(lookback_bars=12, horizon_bars=3, min_training_samples=30)
    model.fit(rows, dataset_fingerprint="dataset-1", code_commit_sha="abc123")
    splits = {"holdout": (192, 240)}

    by_time = {}
    for row in rows:
        by_time[row.event_time_ms] = HistoricalQuote(
            event_time_ms=row.event_time_ms,
            bid=row.close - Decimal("0.01"),
            ask=row.close + Decimal("0.01"),
        )

    result = evaluate_split_with_quotes(
        model,
        rows,
        split="holdout",
        start_index=splits["holdout"][0],
        end_index=splits["holdout"][1],
        quote_provider=lambda timestamp: by_time.get(timestamp),
        max_quote_gap_ms=0,
        slippage_one_way_bps=Decimal("0"),
        commission_one_way_bps=Decimal("0"),
        financing_bps_per_day=Decimal("0"),
        delay_bars=1,
    )
    assert result.n > 0
    assert result.missing_entry_quote == 0
    assert result.missing_exit_quote == 0
    assert result.mean_entry_spread_bps > 0


def test_quote_aware_replay_counts_missing_quotes():
    rows = bars(240)
    model = TSMOMForecastModel(lookback_bars=12, horizon_bars=3, min_training_samples=30)
    model.fit(rows, dataset_fingerprint="dataset-1", code_commit_sha="abc123")
    result = evaluate_split_with_quotes(
        model,
        rows,
        split="holdout",
        start_index=192,
        end_index=240,
        quote_provider=lambda timestamp: None,
        max_quote_gap_ms=0,
        delay_bars=1,
    )
    assert result.n == 0
    assert result.missing_entry_quote > 0
