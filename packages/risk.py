from decimal import Decimal, ROUND_DOWN
from .models import InstrumentSpec, PortfolioState

D0 = Decimal('0')

def floor_step(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0: raise ValueError('step must be positive')
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step

def cash_risk_per_lot(spec: InstrumentSpec, stop_distance: Decimal, *, quote_to_account: Decimal = Decimal('1')) -> Decimal:
    """Cash loss per one broker lot using broker tick_size/tick_value.
    Production adapters should cross-check this with the broker's own calculators."""
    if stop_distance <= 0 or spec.tick_size <= 0 or spec.tick_value <= 0 or quote_to_account <= 0:
        raise ValueError('invalid stop/tick/conversion inputs')
    ticks = stop_distance / spec.tick_size
    return ticks * spec.tick_value * quote_to_account

def size_for_cash_risk(spec: InstrumentSpec, equity: Decimal, risk_fraction: Decimal, stop_distance: Decimal,
                       *, quote_to_account: Decimal = Decimal('1')) -> Decimal:
    if equity <= 0 or risk_fraction <= 0: return D0
    budget = equity * risk_fraction
    per_lot = cash_risk_per_lot(spec, stop_distance, quote_to_account=quote_to_account)
    raw_lots = budget / per_lot
    # Never force the broker minimum when it would exceed the risk budget.
    # Safe result is NO-SIZE / NO-TRADE; orchestration must handle that explicitly.
    if raw_lots < spec.min_volume:
        return D0
    clipped = min(raw_lots, spec.max_volume)
    sized = floor_step(clipped, spec.volume_step)
    return sized if sized >= spec.min_volume else D0

def verify_post_trade_risk(after: PortfolioState, max_gross: Decimal, max_drawdown: Decimal) -> bool:
    return (not after.frozen and after.gross_risk_fraction <= max_gross and after.account_drawdown_fraction <= max_drawdown)
