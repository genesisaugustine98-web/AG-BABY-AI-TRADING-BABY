from decimal import Decimal
from packages.execution_tca import TCAObservation, signed_slippage_fraction

def test_tca_signs_slippage_for_buy_and_sell():
    assert signed_slippage_fraction(side="BUY", decision_mid=Decimal("100"), execution_price=Decimal("101")) == Decimal("0.01")
    assert signed_slippage_fraction(side="SELL", decision_mid=Decimal("100"), execution_price=Decimal("99")) == Decimal("0.01")

def test_tca_computes_quote_shortfall_and_all_in_cost():
    obs=TCAObservation.from_fill(environment="demo",order_id="o1",broker_order_id="b1",strategy_id="s1",model_id="m",model_version="1",
        instrument="EURUSD",side="BUY",requested_quantity=Decimal("2"),filled_quantity=Decimal("2"),decision_mid=Decimal("100"),
        execution_price=Decimal("101"),arrival_spread=Decimal("1"),commission=Decimal("2"),financing=Decimal("0"),
        observed_at="2026-09-23T00:00:00+00:00")
    assert obs.slippage_bps==Decimal("100"); assert obs.spread_bps==Decimal("100"); assert obs.implementation_shortfall_quote==Decimal("2")

def test_tca_signed_financing_can_reduce_cost():
    obs=TCAObservation.from_fill(environment="demo",order_id="o1",broker_order_id="b1",strategy_id="s1",model_id="m",model_version="1",
        instrument="EURUSD",side="BUY",requested_quantity=Decimal("1"),filled_quantity=Decimal("1"),decision_mid=Decimal("100"),
        execution_price=Decimal("100"),arrival_spread=Decimal("0"),commission=Decimal("1"),financing=Decimal("-0.5"),
        observed_at="2026-09-23T00:00:00+00:00")
    assert obs.total_cost_fraction==Decimal("0.005")
