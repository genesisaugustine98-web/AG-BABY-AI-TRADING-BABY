from decimal import Decimal
from packages.fx_valuation import USDConversionGraph
from apps.trading_runtime.canonical import CanonicalPortfolioRiskGate

class Quote:
    def __init__(self,mid): self.mid=Decimal(str(mid))

class Spec:
    base_ccy="EUR"; quote_ccy="GBP"; contract_size=Decimal("100000"); symbol="EURGBP"

def test_canonical_gate_values_cross_currency_notional_in_usd():
    graph=USDConversionGraph({"EURGBP":Decimal("0.85"),"GBPUSD":Decimal("1.25")})
    result=CanonicalPortfolioRiskGate._usd_notional(quantity=Decimal("1"),quote=Quote("0.85"),spec=Spec(),fx=graph)
    assert result==Decimal("106250")
