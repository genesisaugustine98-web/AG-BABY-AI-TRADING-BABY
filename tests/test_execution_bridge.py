from datetime import datetime, timezone
from decimal import Decimal

from packages.execution_bridge import GovernedExecutionBridge, RegisteredModel
from packages.intelligence_mesh import ModelForecast
from packages.models import InstrumentSpec, EventState, MarketState
from packages.opportunity import build_candidate


def make_forecast():
    return ModelForecast(
        "model-a",
        "1",
        datetime(2026, 9, 19, 11, 0, tzinfo=timezone.utc),
        300,
        Decimal("0.002"),
        Decimal("0.70"),
        Decimal("0.80"),
        "features-a",
        ("e1", "e2"),
    )


def make_candidate():
    market = MarketState(
        EventState.NORMAL,
        100,
        Decimal("0.0001"),
        Decimal("0.90"),
        Decimal("0.10"),
        Decimal("0.95"),
        Decimal("0.95"),
    )
    return build_candidate(
        instrument="USDJPY",
        forecast=make_trade_forecast(),
        market=market,
        estimated_cost=Decimal("0.0001"),
        safety_margin=Decimal("0.0001"),
        base_risk=Decimal("0.001"),
        evidence_ids=("e1", "e2"),
    )


def make_trade_forecast():
    from packages.models import Forecast
    return Forecast(
        "model-a",
        "1",
        int(datetime(2026, 9, 19, 11, 0, tzinfo=timezone.utc).timestamp() * 1000),
        300,
        Decimal("0.002"),
        "fraction",
        Decimal("0.70"),
        Decimal("0.80"),
        Decimal("0.80"),
    )


def make_instrument():
    return InstrumentSpec(
        "USDJPY", "USD", "JPY",
        Decimal("100000"), Decimal("0.001"), Decimal("0.001"),
        Decimal("1"), Decimal("0.01"), Decimal("100"), Decimal("0.01"),
    )


def registered(*, status="validated", calibration=Decimal("0.80"), execution_grade=False):
    return RegisteredModel(
        "model-a", "1", status, "dataset-a", "abc123",
        calibration, execution_grade, "features-a",
    )


def test_bridge_denies_unvalidated_model():
    result = GovernedExecutionBridge().build_intent(
        strategy_id="strategy-a",
        strategy_id="strategy-a",
        strategy_id="strategy-a",
        candidate=make_candidate(),
        forecast=make_forecast(),
        registered_model=registered(status="candidate"),
        instrument=make_instrument(),
        quantity=Decimal("0.01"),
        stop_price=149,
        target_price=151,
        now_ms=int(datetime(2026, 9, 19, 11, 1, tzinfo=timezone.utc).timestamp() * 1000),
        expires_at_ms=int(datetime(2026, 9, 19, 11, 2, tzinfo=timezone.utc).timestamp() * 1000),
        max_slippage_fraction=Decimal("0.0001"),
        horizon_seconds=300,
    )
    assert not result.approved
    assert "MODEL_NOT_VALIDATED_FOR_DEMO" in result.reasons
    assert result.intent is None


def test_bridge_requires_provenance():
    candidate = make_candidate()
    candidate = candidate.__class__(**{**candidate.__dict__, "evidence_ids": ()})
    result = GovernedExecutionBridge().build_intent(
        strategy_id="strategy-a",
        candidate=candidate,
        forecast=make_forecast(),
        registered_model=registered(),
        instrument=make_instrument(),
        quantity=Decimal("0.01"),
        stop_price=149,
        target_price=151,
        now_ms=int(datetime(2026, 9, 19, 11, 1, tzinfo=timezone.utc).timestamp() * 1000),
        expires_at_ms=int(datetime(2026, 9, 19, 11, 2, tzinfo=timezone.utc).timestamp() * 1000),
        max_slippage_fraction=Decimal("0.0001"),
        horizon_seconds=300,
    )
    assert "EVIDENCE_PROVENANCE_REQUIRED" in result.reasons


def test_bridge_builds_intent_from_admitted_candidate():
    result = GovernedExecutionBridge().build_intent(
        candidate=make_candidate(),
        forecast=make_forecast(),
        registered_model=registered(),
        instrument=make_instrument(),
        quantity=Decimal("0.01"),
        stop_price=149,
        target_price=151,
        now_ms=int(datetime(2026, 9, 19, 11, 1, tzinfo=timezone.utc).timestamp() * 1000),
        expires_at_ms=int(datetime(2026, 9, 19, 11, 2, tzinfo=timezone.utc).timestamp() * 1000),
        max_slippage_fraction=Decimal("0.0001"),
        horizon_seconds=300,
    )
    assert result.approved
    assert result.intent is not None
    assert result.intent.strategy_id == "model-a"
    assert result.intent.evidence_ids == frozenset({"e1", "e2"})


def test_bridge_requires_forecast_registry_calibration_match():
    result = GovernedExecutionBridge().build_intent(
        candidate=make_candidate(),
        forecast=make_forecast(),
        registered_model=registered(calibration=Decimal("0.79")),
        instrument=make_instrument(),
        quantity=Decimal("0.01"),
        stop_price=149,
        target_price=151,
        now_ms=int(datetime(2026, 9, 19, 11, 1, tzinfo=timezone.utc).timestamp() * 1000),
        expires_at_ms=int(datetime(2026, 9, 19, 11, 2, tzinfo=timezone.utc).timestamp() * 1000),
        max_slippage_fraction=Decimal("0.0001"),
        horizon_seconds=300,
    )
    assert "FORECAST_CALIBRATION_MISMATCH" in result.reasons
