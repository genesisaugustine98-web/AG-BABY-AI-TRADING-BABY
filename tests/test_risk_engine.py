from decimal import Decimal

from packages.models import AdmissionContext, EventState, Forecast, InstrumentSpec, MarketState, PortfolioState, Quote, TradeIntent
from packages.risk_engine import DeterministicRiskEngine, RiskLimits


def spec():
    return InstrumentSpec("USDJPY", "USD", "JPY", Decimal("100000"), Decimal("0.001"), Decimal("0.001"), Decimal("1"), Decimal("0.01"), Decimal("100"), Decimal("0.01"))


def intent():
    return TradeIntent("i1", "s1", "v1", "p1", "USDJPY", "BUY", Decimal("0.9"), "MARKET", None, Decimal("149.0"), Decimal("152.0"), 1000, 2000, Decimal("0.001"), Decimal("0.005"), 300, frozenset({"e1"}))


def context(**changes):
    values = dict(
        now_ms=2000,
        quote=Quote("USDJPY", Decimal("150.0"), Decimal("150.002"), 1999, "demo"),
        forecast=Forecast("m", "1", 1000, 300, Decimal("0.002"), "fraction", Decimal("0.70"), Decimal("0.80"), Decimal("0.80")),
        market=MarketState(EventState.NORMAL, 20, Decimal("0.00001"), Decimal("0.90"), Decimal("0.10"), Decimal("0.95"), Decimal("0.95")),
        portfolio=PortfolioState(Decimal("100000"), Decimal("0"), Decimal("0.01"), Decimal("1"), 1, Decimal("0.01"), Decimal("0"), False),
        estimated_cost_fraction=Decimal("0.0002"),
        safety_margin_fraction=Decimal("0.0001"),
    )
    values.update(changes)
    return AdmissionContext(**values)


def test_risk_engine_approves_normal_order():
    result = DeterministicRiskEngine().evaluate(intent=intent(), context=context(), instrument=spec())
    assert result.approved
    assert not result.reasons
    assert result.order_risk_fraction > 0


def test_risk_engine_rejects_frozen_account():
    frozen = context(portfolio=PortfolioState(Decimal("100000"), Decimal("0"), Decimal("0.01"), Decimal("1"), 1, Decimal("0.01"), Decimal("0"), True))
    result = DeterministicRiskEngine().evaluate(intent=intent(), context=frozen, instrument=spec())
    assert not result.approved
    assert "ACCOUNT_FROZEN" in result.reasons


def test_risk_engine_rejects_bad_stop_side():
    bad = context()
    bad_intent = TradeIntent(**{**intent().__dict__, "stop_price": Decimal("151")})
    result = DeterministicRiskEngine().evaluate(intent=bad_intent, context=bad, instrument=spec())
    assert not result.approved
    assert "BUY_STOP_NOT_BELOW_MARKET" in result.reasons


def test_risk_engine_rejects_order_risk_over_limit():
    limits = RiskLimits(max_order_risk=Decimal("0.0001"))
    result = DeterministicRiskEngine(limits).evaluate(intent=intent(), context=context(), instrument=spec())
    assert not result.approved
    assert "ORDER_RISK_LIMIT" in result.reasons


def test_risk_engine_accepts_valid_volume_anchored_at_minimum():
    instrument = InstrumentSpec(
        'USDJPY', 'USD', 'JPY',
        Decimal('100000'), Decimal('0.001'), Decimal('0.001'),
        Decimal('1'), Decimal('0.03'), Decimal('100'), Decimal('0.05')
    )
    trade = TradeIntent(**{**intent().__dict__, 'quantity': Decimal('0.08')})
    result = DeterministicRiskEngine().evaluate(
        intent=trade,
        context=context(),
        instrument=instrument,
    )
    assert result.approved
    assert 'BROKER_VOLUME_STEP' not in result.reasons
