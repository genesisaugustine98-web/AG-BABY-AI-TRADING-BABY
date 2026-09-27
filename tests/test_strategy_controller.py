from decimal import Decimal

from packages.models import EventState, MarketState
from packages.strategy_controller import TSMOMController
from packages.tsmom_forecast import PriceBar, TSMOMForecastModel


def bars(n=180):
    result = []
    close = Decimal("1")
    for i in range(n):
        close += Decimal("0.0005") if i % 4 != 0 else Decimal("0.0003")
        t = 1_000_000 + i * 3_600_000
        result.append(PriceBar("EURUSD", t, t + 3_600_000, close, "test", "1", f"bar-{i}"))
    return result


def fit_model():
    model = TSMOMForecastModel(
        lookback_bars=8,
        horizon_bars=3,
        min_training_samples=20,
        bar_interval_seconds=3600,
    )
    model.fit(bars(), dataset_fingerprint="d", code_commit_sha="c")
    return model


def market():
    return MarketState(
        EventState.NORMAL,
        100,
        Decimal("0.00001"),
        Decimal("0.90"),
        Decimal("0.10"),
        Decimal("0.95"),
        Decimal("0.99"),
    )


def test_tsmom_controller_emits_auditable_candidate():
    controller = TSMOMController(fit_model(), ("EURUSD",))
    decision = controller.evaluate(
        symbol="EURUSD",
        bars=bars(),
        market=market(),
        decision_time_ms=bars()[-1].usable_at_ms,
        estimated_cost=Decimal("0.0001"),
        safety_margin=Decimal("0.0001"),
    )
    assert decision is not None
    assert decision.forecast.evidence_ids
    assert decision.candidate.candidate_id.startswith("opp-")
