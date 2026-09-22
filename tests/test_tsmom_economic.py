from dataclasses import replace
from decimal import Decimal

from packages.tsmom_economic import chronological_split_indices, evaluate_split, evaluate_split_sensitivity
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


def test_economic_validation_skips_zero_momentum_without_aborting():
    rows = bars(240)
    model = TSMOMForecastModel(lookback_bars=12, horizon_bars=3, min_training_samples=30)
    model.fit(rows, dataset_fingerprint="dataset-1", code_commit_sha="abc123")
    target_index = 160
    rows[target_index] = replace(rows[target_index], close=rows[target_index - 12].close)
    splits = chronological_split_indices(len(rows))
    result = evaluate_split(
        model, rows, split="validation",
        start_index=splits["validation"][0], end_index=splits["validation"][1],
        one_way_cost_bps=Decimal("0"), delay_bars=1,
    )
    assert result.skipped_no_signal >= 1
    assert result.n > 0



def test_economic_sensitivity_replays_each_split_once_semantically():
    rows = bars(240)
    model = TSMOMForecastModel(lookback_bars=12, horizon_bars=3, min_training_samples=30)
    model.fit(rows, dataset_fingerprint="dataset-1", code_commit_sha="abc123")
    splits = chronological_split_indices(len(rows))
    results = evaluate_split_sensitivity(
        model,
        rows,
        split="holdout",
        start_index=splits["holdout"][0],
        end_index=splits["holdout"][1],
        one_way_costs_bps=(Decimal("0"), Decimal("10")),
        delay_bars=1,
    )
    assert set(results) == {Decimal("0"), Decimal("10")}
    assert results[Decimal("0")].n == results[Decimal("10")].n
    assert results[Decimal("10")].mean_net < results[Decimal("0")].mean_net
