from decimal import Decimal
from dataclasses import replace
from packages.models import *
from packages.policy import AdmissionPolicy

def base():
    now=1_000_000
    return AdmissionContext(now, Quote('EURUSD',Decimal('1.10000'),Decimal('1.10001'),now,'demo'),
        Forecast('m','1',now-1000,3600,Decimal('0.0040'),'fraction',Decimal('0.61'),Decimal('0.80'),Decimal('0.80')),
        MarketState(EventState.NORMAL,100,Decimal('0.00001'),Decimal('0.90'),Decimal('0.10'),Decimal('0.95'),Decimal('0.99')),
        PortfolioState(Decimal('10000'),Decimal('0'),Decimal('0.01'),Decimal('0'),0,Decimal('0.01'),Decimal('0.005')),
        Decimal('0.0010'),Decimal('0.0005'))

def test_approve(): assert AdmissionPolicy().evaluate(base())[0] == Decision.APPROVE

def test_future_quote_is_rejected():
    c=replace(base(), market=MarketState(EventState.NORMAL,-1,Decimal('0.00001'),Decimal('0.90'),Decimal('0.10'),Decimal('0.95'),Decimal('0.99')))
    decision, reasons = AdmissionPolicy().evaluate(c)
    assert decision == Decision.DENY
    assert 'FUTURE_QUOTE_TIMESTAMP' in reasons

def test_stale():
    c=replace(base(), market=MarketState(EventState.NORMAL,5000,Decimal('0.00001'),Decimal('0.90'),Decimal('0.10'),Decimal('0.95'),Decimal('0.99')))
    assert AdmissionPolicy().evaluate(c)[0] == Decision.DENY

def test_event():
    c=replace(base(), market=MarketState(EventState.IMMEDIATE_EVENT,100,Decimal('0.00001'),Decimal('0.90'),Decimal('0.10'),Decimal('0.95'),Decimal('0.99')))
    assert AdmissionPolicy().evaluate(c)[0] == Decision.DENY

def test_unit_mismatch():
    c=replace(base(), forecast=Forecast('m','1',999000,3600,Decimal('10'),'pips',Decimal('0.61'),Decimal('0.80'),Decimal('0.80')))
    assert AdmissionPolicy().evaluate(c)[0] == Decision.DENY
