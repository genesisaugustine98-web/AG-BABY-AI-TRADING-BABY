from decimal import Decimal
from .models import AdmissionContext, Decision, EventState

class AdmissionPolicy:
    def __init__(self, *, max_quote_age_ms: int = 1500, max_spread_frac: Decimal = Decimal('0.0003'),
                 min_probability: Decimal = Decimal('0.55'), min_calibration: Decimal = Decimal('0.65'),
                 min_executable_edge: Decimal = Decimal('0.0001'), min_liquidity: Decimal = Decimal('0.55'),
                 max_intervention: Decimal = Decimal('0.70'), max_broker_stress: Decimal = Decimal('0.50'),
                 max_data_stress: Decimal = Decimal('0.50'), max_gross_risk: Decimal = Decimal('0.03'),
                 max_drawdown: Decimal = Decimal('0.08')):
        self.max_quote_age_ms=max_quote_age_ms; self.max_spread_frac=max_spread_frac
        self.min_probability=min_probability; self.min_calibration=min_calibration
        self.min_executable_edge=min_executable_edge; self.min_liquidity=min_liquidity
        self.max_intervention=max_intervention; self.max_broker_stress=max_broker_stress; self.max_data_stress=max_data_stress
        self.max_gross_risk=max_gross_risk; self.max_drawdown=max_drawdown

    def evaluate(self, ctx: AdmissionContext) -> tuple[Decision, list[str]]:
        reasons=[]
        if ctx.portfolio.frozen: reasons.append('ACCOUNT_FROZEN')
        if ctx.market.data_health < Decimal('0.80'): reasons.append('DATA_HEALTH')
        if ctx.market.broker_health < Decimal('0.80'): reasons.append('BROKER_HEALTH')
        if ctx.market.broker_health < self.max_broker_stress: reasons.append('BROKER_STRESS')
        if ctx.market.data_health < self.max_data_stress: reasons.append('DATA_STRESS')
        if ctx.market.quote_age_ms < 0: reasons.append('FUTURE_QUOTE_TIMESTAMP')
        elif ctx.market.quote_age_ms > self.max_quote_age_ms: reasons.append('STALE_QUOTE')
        if ctx.market.spread_fraction_of_price > self.max_spread_frac: reasons.append('WIDE_SPREAD')
        if ctx.market.liquidity_score < self.min_liquidity: reasons.append('LOW_LIQUIDITY')
        if ctx.market.intervention_score >= self.max_intervention: reasons.append('INTERVENTION_RISK')
        if ctx.market.event_state in {EventState.IMMEDIATE_EVENT, EventState.INTERVENTION_RISK, EventState.BROKER_STRESS, EventState.DATA_STRESS}:
            reasons.append(f'BLOCKED_EVENT_STATE:{ctx.market.event_state.value}')
        if ctx.forecast.generated_at_ms > ctx.now_ms: reasons.append('FUTURE_FORECAST_TIMESTAMP')
        if ctx.forecast.probability_up < self.min_probability: reasons.append('LOW_PROBABILITY')
        if ctx.forecast.calibration_score < self.min_calibration: reasons.append('BAD_CALIBRATION')
        if ctx.forecast.expected_return_unit != 'fraction': reasons.append('FORECAST_UNIT_MISMATCH')
        executable_edge = ctx.forecast.expected_return - ctx.estimated_cost_fraction - ctx.safety_margin_fraction
        if executable_edge < self.min_executable_edge: reasons.append('EDGE_BELOW_EXECUTABLE_THRESHOLD')
        if ctx.portfolio.gross_risk_fraction > self.max_gross_risk: reasons.append('GROSS_RISK_LIMIT')
        if ctx.portfolio.account_drawdown_fraction > self.max_drawdown: reasons.append('DRAWDOWN_LIMIT')
        return (Decision.DENY, reasons) if reasons else (Decision.APPROVE, [])
