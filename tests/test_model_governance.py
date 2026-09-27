from decimal import Decimal

from packages.model_governance import ModelEvidence, ModelGovernance, ModelState


def evidence(complete=True):
    return ModelEvidence(
        point_in_time=complete,
        walk_forward=complete,
        purged_validation=complete,
        costs_modeled=complete,
        slippage_modeled=complete,
        multiple_testing_controlled=complete,
        calibrated=complete,
        stress_tested=complete,
        calibration_score=Decimal("0.80") if complete else Decimal("0.60"),
        max_drawdown_fraction=Decimal("0.05"),
        demo_validated=complete,
        data_fingerprint="data" if complete else "",
        code_commit_sha="commit" if complete else "",
    )


def test_demo_promotion_requires_complete_evidence():
    decision = ModelGovernance().transition(
        current=ModelState.PAPER,
        target=ModelState.DEMO,
        evidence=evidence(False),
    )
    assert not decision.allowed
    assert "PROMOTION_EVIDENCE_INCOMPLETE" in decision.reasons


def test_complete_demo_promotion_is_allowed():
    decision = ModelGovernance().transition(
        current=ModelState.PAPER,
        target=ModelState.DEMO,
        evidence=evidence(True),
    )
    assert decision.allowed


def test_retirement_is_always_explicitly_available():
    decision = ModelGovernance().transition(
        current=ModelState.DEMO,
        target=ModelState.RETIRED,
        evidence=None,
    )
    assert decision.allowed
