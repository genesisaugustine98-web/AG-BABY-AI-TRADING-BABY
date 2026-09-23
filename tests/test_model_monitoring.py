from decimal import Decimal
import pytest

from packages.model_monitoring import DriftLimits, brier_score, evaluate_drift, population_stability_index


def test_identical_distribution_has_zero_psi():
    distribution = [Decimal("25"), Decimal("25"), Decimal("50")]
    assert population_stability_index(distribution, distribution) == Decimal("0")


def test_brier_score_is_bounded():
    score = brier_score([Decimal("0.9"), Decimal("0.1")], [1, 0])
    assert Decimal("0") <= score <= Decimal("1")


def test_high_drift_is_rejected():
    result = evaluate_drift(
        expected_distribution=[Decimal("90"), Decimal("10")],
        actual_distribution=[Decimal("10"), Decimal("90")],
        limits=DriftLimits(max_psi=Decimal("0.20"), max_brier_score=Decimal("0.25")),
    )
    assert not result.allowed
    assert "FEATURE_DISTRIBUTION_PSI_LIMIT" in result.reasons


def test_invalid_inputs_fail():
    with pytest.raises(ValueError):
        brier_score([Decimal("1.2")], [1])
