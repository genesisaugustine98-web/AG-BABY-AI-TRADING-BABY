from decimal import Decimal
from datetime import datetime, timezone

from packages.intelligence_mesh import Evidence, ModelForecast, ensemble_forecasts, point_in_time_evidence
from packages.models import EventState, Forecast, MarketState
from packages.opportunity import build_candidate
from packages.research_quality import benjamini_hochberg, brier_score, expected_calibration_error, max_drawdown


def market():
    return MarketState(EventState.NORMAL, 10, Decimal("0.00001"), Decimal("0.90"), Decimal("0.10"), Decimal("0.95"), Decimal("0.95"))


def forecast():
    return Forecast("m", "1", 1000, 300, Decimal("0.002"), "fraction", Decimal("0.70"), Decimal("0.80"), Decimal("0.80"))


def test_candidate_requires_executable_edge():
    candidate = build_candidate(instrument="USDJPY", forecast=forecast(), market=market(), estimated_cost=Decimal("0.0002"), safety_margin=Decimal("0.0001"))
    assert candidate.state == "ADMITTED"
    assert candidate.side == "BUY"
    assert candidate.executable_edge == Decimal("0.0017")


def test_candidate_blocks_stressed_market():
    stressed = MarketState(EventState.DATA_STRESS, 10, Decimal("0.00001"), Decimal("0.90"), Decimal("0.10"), Decimal("0.95"), Decimal("0.50"))
    candidate = build_candidate(instrument="USDJPY", forecast=forecast(), market=stressed, estimated_cost=Decimal("0.0002"))
    assert candidate.state == "REJECTED"


def test_bh_controls_multiple_testing():
    result = benjamini_hochberg([Decimal("0.001"), Decimal("0.02"), Decimal("0.20")], alpha=Decimal("0.05"))
    assert result.rejected_indices == (0, 1)


def test_calibration_and_brier_are_explicit_metrics():
    probabilities = [Decimal("0.9"), Decimal("0.1"), Decimal("0.8"), Decimal("0.2")]
    outcomes = [1, 0, 1, 0]
    assert brier_score(probabilities, outcomes) == Decimal("0.025")
    assert expected_calibration_error(probabilities, outcomes) == Decimal("0")


def test_max_drawdown_is_peak_to_trough():
    assert max_drawdown([Decimal("0.10"), Decimal("-0.20"), Decimal("0.05")]) == Decimal("0.12")


def test_pit_evidence_filters_unreleased_data():
    now = datetime(2026, 9, 17, tzinfo=timezone.utc)
    evidence = (
        Evidence("e1", "fred", "v1", now, now, "USDJPY", "rate", Decimal("1")),
        Evidence("e2", "news", "v1", now, now.replace(hour=11), "USDJPY", "headline", "bad"),
    )
    usable = point_in_time_evidence(evidence, datetime(2026, 9, 17, 10, tzinfo=timezone.utc))
    assert [item.evidence_id for item in usable] == ["e1"]


def test_forecast_ensemble_is_equal_weight_and_provenance_preserving():
    now = datetime(2026, 9, 17, tzinfo=timezone.utc)
    forecasts = (
        ModelForecast("a", "1", now, 300, Decimal("0.001"), Decimal("0.60"), Decimal("0.70"), "fa", ("e1",)),
        ModelForecast("b", "1", now, 300, Decimal("0.003"), Decimal("0.80"), Decimal("0.90"), "fb", ("e2",)),
    )
    result = ensemble_forecasts(forecasts)
    assert result.expected_return == Decimal("0.002")
    assert result.probability_up == Decimal("0.70")
    assert result.evidence_ids == ("e1", "e2")
