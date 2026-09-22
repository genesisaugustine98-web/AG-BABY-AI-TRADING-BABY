import pytest
from decimal import Decimal
from packages.models import InstrumentSpec
from packages.risk import size_for_cash_risk, cash_risk_per_lot

def test_fx_lot_sizing_uses_tick_value():
    spec=InstrumentSpec('EURUSD','EUR','USD',Decimal('100000'),Decimal('0.00001'),Decimal('0.00001'),Decimal('1'),Decimal('0.01'),Decimal('100'),Decimal('0.01'))
    size=size_for_cash_risk(spec,Decimal('10000'),Decimal('0.01'),Decimal('0.00100'))
    assert size == Decimal('1.00')


def test_min_volume_never_exceeds_cash_risk_budget():
    spec = InstrumentSpec('EURUSD','EUR','USD',Decimal('100000'),Decimal('0.00001'),Decimal('0.00001'),Decimal('10'),Decimal('1'),Decimal('100'),Decimal('1'))
    lots = size_for_cash_risk(spec, Decimal('1000'), Decimal('0.001'), Decimal('0.01'))
    assert lots == Decimal('0')


def test_invalid_stop_rejected():
    spec = InstrumentSpec('EURUSD','EUR','USD',Decimal('100000'),Decimal('0.00001'),Decimal('0.00001'),Decimal('1'),Decimal('0.01'),Decimal('100'),Decimal('0.01'))
    with pytest.raises(ValueError):
        cash_risk_per_lot(spec, Decimal('0'))
    with pytest.raises(ValueError):
        cash_risk_per_lot(spec, Decimal('-0.001'))


def test_fx_lot_sizing_honors_minimum_volume_offset():
    spec = InstrumentSpec(
        'EURUSD', 'EUR', 'USD',
        Decimal('100000'), Decimal('0.00001'), Decimal('0.00001'),
        Decimal('1'), Decimal('0.03'), Decimal('10'), Decimal('0.05')
    )
    lots = size_for_cash_risk(spec, Decimal('10000'), Decimal('0.01'), Decimal('0.0125'))
    assert lots == Decimal('0.08')
