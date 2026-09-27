from decimal import Decimal

from packages.opportunity import OpportunityCandidate
from packages.strategy_allocator import AllocationLimits, StrategyAllocator


def candidate(candidate_id, strategy_id, instrument, risk, model_id=None):
    model_id = model_id or strategy_id
    return OpportunityCandidate(
        candidate_id,
        instrument,
        "BUY",
        Decimal("0.01"),
        Decimal("0.60"),
        Decimal("0.80"),
        Decimal("0.001"),
        Decimal("0.0001"),
        Decimal("0.002"),
        Decimal(str(risk)),
        "ADMITTED",
        model_id,
        "1",
        (),
        "executable",
        strategy_id,
    )


def test_allocator_applies_declared_risk_budgets():
    candidates = (
        candidate("b", "carry", "EURUSD", "0.006"),
        candidate("a", "tsmom", "EURUSD", "0.006"),
        candidate("c", "tsmom", "GBPUSD", "0.006"),
    )
    result = StrategyAllocator(
        AllocationLimits(
            max_total_risk=Decimal("0.012"),
            max_per_strategy_risk=Decimal("0.012"),
            max_per_instrument_risk=Decimal("0.010"),
            max_candidates=8,
        )
    ).allocate(candidates=candidates, strategy_order=("tsmom", "carry"))
    assert [x.candidate_id for x in result.approved] == ["a", "c"]
    assert ("b", "TOTAL_RISK_LIMIT") in result.rejected
    assert result.total_risk == Decimal("0.012")
