from decimal import Decimal

from packages.horizon import Timeframe
from packages.multihorizon_decision import make_proposal


def test_multihorizon_proposal_is_not_an_order():
    proposal = make_proposal(
        forecasts={
            Timeframe.D1: Decimal("0.4"),
            Timeframe.H4: Decimal("0.7"),
            Timeframe.H1: Decimal("0.8"),
        },
        expected_hold_seconds=3600,
        execution_latency_seconds=5,
    )
    assert proposal.direction == 1
    assert proposal.timeframe == Timeframe.H1
    assert "MULTI_HORIZON_CONSENSUS" in proposal.reason_codes


def test_multihorizon_disagreement_is_visible():
    proposal = make_proposal(
        forecasts={
            Timeframe.H1: Decimal("0.9"),
            Timeframe.M15: Decimal("-0.8"),
        },
        expected_hold_seconds=900,
        execution_latency_seconds=5,
    )
    assert "HIGH_HORIZON_DISAGREEMENT" in proposal.reason_codes
