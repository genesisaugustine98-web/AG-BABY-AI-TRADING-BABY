from packages.research_promotion_gate import evaluate_research_package


def evidence(**overrides):
    value = {
        "independent_validation_periods": 3,
        "cost_stress_points": 2,
        "slippage_stress_points": 2,
        "untouched_holdout": True,
        "regime_coverage": True,
        "selection_lock": True,
        "research_run_id": "run-1",
        "research_commit_sha": "abc",
        "evaluation_dataset_fingerprint": "data",
    }
    value.update(overrides)
    return value


def test_complete_research_package_is_eligible_for_governance():
    assert evaluate_research_package(evidence()).allowed


def test_single_holdout_does_not_satisfy_independent_validation_requirement():
    result = evaluate_research_package(evidence(independent_validation_periods=1))
    assert not result.allowed
    assert "INSUFFICIENT_INDEPENDENT_VALIDATION_PERIODS" in result.reasons


def test_missing_lineage_blocks_promotion():
    result = evaluate_research_package(evidence(research_commit_sha=""))
    assert not result.allowed
    assert "RESEARCH_LINEAGE_MISSING:research_commit_sha" in result.reasons
