from decimal import Decimal

from packages.tsmom_economic import chronological_split_indices, evaluate_split
from packages.tsmom_forecast import TSMOMForecastModel
from tests.test_tsmom_forecast import bars


def test_split_indices_are_chronological_and_non_overlapping():
    splits = chronological_split_indices(100)
    assert splits["development"] == (0, 60)
    assert splits["validation"] == (60, 80)
    assert splits["holdout"] == (80, 100)


def test_cost_reduces_mean_net_return():
    rows = bars(240)
    model = TSMOMForecastModel(lookback_bars=12, horizon_bars=3, min_training_samples=30)
    model.fit(rows, dataset_fingerprint="dataset-1", code_commit_sha="abc123")
    splits = chronological_split_indices(len(rows))
    free = evaluate_split(
        model, rows, split="holdout",
        start_index=splits["holdout"][0], end_index=splits["holdout"][1],
        one_way_cost_bps=Decimal("0"),
    )
    costly = evaluate_split(
        model, rows, split="holdout",
        start_index=splits["holdout"][0], end_index=splits["holdout"][1],
        one_way_cost_bps=Decimal("10"),
    )
    assert free.n == costly.n
    assert costly.mean_net < free.mean_net
    assert costly.cumulative_net <= free.cumulative_net


def test_economic_validation_handles_delay():
    rows = bars(240)
    model = TSMOMForecastModel(lookback_bars=12, horizon_bars=3, min_training_samples=30)
    model.fit(rows, dataset_fingerprint="dataset-1", code_commit_sha="abc123")
    splits = chronological_split_indices(len(rows))
    result = evaluate_split(
        model, rows, split="validation",
        start_index=splits["validation"][0], end_index=splits["validation"][1],
        one_way_cost_bps=Decimal("2"), delay_bars=1,
    )
    assert result.n > 0
    assert result.horizon_bars == 3
    assert result.delay_bars == 1
