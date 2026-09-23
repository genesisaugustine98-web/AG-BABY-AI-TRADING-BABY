from decimal import Decimal

from packages.institutional_risk import (
    InstitutionalAllocationLimits,
    InstitutionalStrategyAllocator,
    correlations_from_env_payload,
)
from packages.opportunity import OpportunityCandidate


def candidate(candidate_id, instrument, side="BUY", risk="0.005", strategy="s1"):
    return OpportunityCandidate(
        candidate_id,
        instrument,
        side,
        Decimal("0.002"),
        Decimal("0.70"),
        Decimal("0.80"),
        Decimal("0.0001"),
        Decimal("0.0001"),
        Decimal("0.0018"),
        Decimal(risk),
        "ADMITTED",
        "model",
        "1",
        (),
        "executable",
        strategy,
    )


def test_missing_correlation_is_a_hard_admission_block_when_required():
    allocator = InstitutionalStrategyAllocator(
        InstitutionalAllocationLimits(
            max_total_risk=Decimal("0.03"),
            max_per_strategy_risk=Decimal("0.03"),
            max_per_instrument_risk=Decimal("0.03"),
            max_candidates=8,
            max_correlation_adjusted_risk=Decimal("0.03"),
            max_abs_net_risk=Decimal("0.03"),
            require_complete_correlations=True,
        )
    )
    result = allocator.allocate(
        candidates=(candidate("a", "EURUSD"), candidate("b", "GBPUSD")),
        strategy_order=("s1",),
    )
    assert [x.candidate_id for x in result.approved] == ["a"]
    assert result.rejected == (("b", "PORTFOLIO_CORRELATION_DATA_INCOMPLETE"),)


def test_known_correlation_controls_concentration():
    allocator = InstitutionalStrategyAllocator(
        InstitutionalAllocationLimits(
            max_total_risk=Decimal("0.03"),
            max_per_strategy_risk=Decimal("0.03"),
            max_per_instrument_risk=Decimal("0.03"),
            max_candidates=8,
            max_correlation_adjusted_risk=Decimal("0.006"),
            max_abs_net_risk=Decimal("0.03"),
            require_complete_correlations=True,
        ),
        correlations={("EURUSD", "GBPUSD"): Decimal("0.99")},
    )
    result = allocator.allocate(
        candidates=(candidate("a", "EURUSD"), candidate("b", "GBPUSD")),
        strategy_order=("s1",),
    )
    assert [x.candidate_id for x in result.approved] == ["a"]
    assert result.rejected == (("b", "PORTFOLIO_CORRELATION_RISK_LIMIT"),)


def test_existing_risk_consumes_total_budget():
    allocator = InstitutionalStrategyAllocator(
        InstitutionalAllocationLimits(
            max_total_risk=Decimal("0.01"),
            max_per_strategy_risk=Decimal("0.02"),
            max_per_instrument_risk=Decimal("0.02"),
            max_candidates=8,
            max_correlation_adjusted_risk=Decimal("0.02"),
            max_abs_net_risk=Decimal("0.02"),
        ),
        current_risk_provider=lambda: Decimal("0.008"),
    )
    result = allocator.allocate(
        candidates=(candidate("a", "EURUSD", risk="0.005"),),
        strategy_order=("s1",),
    )
    assert result.approved == ()
    assert result.rejected == (("a", "TOTAL_RISK_LIMIT"),)


def test_correlation_environment_parser_accepts_common_key_forms():
    result = correlations_from_env_payload('{"EURUSD,GBPUSD":"0.8","USDJPY:EURUSD":0.4}')
    assert result[("EURUSD", "GBPUSD")] == Decimal("0.8")
    assert result[("USDJPY", "EURUSD")] == Decimal("0.4")
