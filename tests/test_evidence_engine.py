from decimal import Decimal

from apps.research.evidence_engine import classify_evidence, compute_stats, cost_breakeven_mean_gross


def test_compute_stats_and_drawdown():
    stats = compute_stats([Decimal("0.10"), Decimal("-0.05"), Decimal("0.02")])
    assert stats.n == 3
    assert stats.mean_net == sum([Decimal("0.10"), Decimal("-0.05"), Decimal("0.02")], Decimal("0")) / Decimal("3")
    assert stats.median_net == Decimal("0.02")
    assert stats.win_rate_net == Decimal("2") / Decimal("3")
    assert stats.cumulative_net > Decimal("0")
    assert stats.max_drawdown < Decimal("0")


def test_empty_is_inconclusive():
    stats = compute_stats([])
    assert classify_evidence(
        stats=stats,
        minimum_n=10,
        minimum_mean_net=Decimal("0"),
    ) == "inconclusive"


def test_small_sample_is_inconclusive():
    stats = compute_stats([Decimal("0.10")])
    assert classify_evidence(
        stats=stats,
        minimum_n=10,
        minimum_mean_net=Decimal("0"),
    ) == "inconclusive"


def test_negative_evidence_is_not_supported():
    stats = compute_stats([Decimal("-0.01")] * 20)
    assert classify_evidence(
        stats=stats,
        minimum_n=10,
        minimum_mean_net=Decimal("0"),
    ) == "not_supported"


def test_cost_breakeven_conversion():
    assert cost_breakeven_mean_gross(Decimal("0.001")) == Decimal("5")
