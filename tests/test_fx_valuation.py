from decimal import Decimal
import pytest
from packages.fx_valuation import USDConversionGraph

def test_direct_and_inverse_usd_rates():
    graph=USDConversionGraph({"EURUSD":Decimal("1.10")})
    assert graph.rate_to_usd("EUR")==Decimal("1.10")
    assert graph.rate_to_usd("USD")==Decimal("1")

def test_cross_currency_conversion():
    graph=USDConversionGraph({"EURGBP":Decimal("0.85"),"GBPUSD":Decimal("1.25")})
    assert graph.rate_to_usd("EUR")==Decimal("1.0625")
    assert graph.quote_notional_usd(base_ccy="EUR",quote_ccy="GBP",units=Decimal("2"),price=Decimal("0.85"))==Decimal("2.125")

def test_missing_conversion_fails_closed():
    with pytest.raises(RuntimeError,match="USD conversion unavailable"):
        USDConversionGraph().rate_to_usd("JPY")
