"""Convert a forecast into an auditable opportunity candidate.

This layer scores economic executability, not trade certainty. It emits data for the
risk engine; it never submits or authorizes broker orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256

from .models import Forecast, MarketState


@dataclass(frozen=True)
class OpportunityCandidate:
    candidate_id: str
    instrument: str
    side: str
    expected_return: Decimal
    probability: Decimal
    calibration_score: Decimal
    estimated_cost: Decimal
    safety_margin: Decimal
    executable_edge: Decimal
    suggested_risk: Decimal
    state: str
    model_id: str
    model_version: str
    evidence_ids: tuple[str, ...]
    reason: str


def build_candidate(
    *,
    instrument: str,
    forecast: Forecast,
    market: MarketState,
    estimated_cost: Decimal,
    safety_margin: Decimal = Decimal("0"),
    min_probability: Decimal = Decimal("0.55"),
    min_calibration: Decimal = Decimal("0.65"),
    min_edge: Decimal = Decimal("0.0001"),
    base_risk: Decimal = Decimal("0.005"),
) -> OpportunityCandidate:
    instrument = instrument.strip().upper()
    if not instrument:
        raise ValueError("instrument must be non-empty")
    if forecast.expected_return_unit != "fraction":
        raise ValueError("forecast expected_return_unit must be fraction")
    if not (Decimal("0") <= forecast.probability_up <= Decimal("1")):
        raise ValueError("probability_up must be in [0,1]")
    if not (Decimal("0") <= forecast.calibration_score <= Decimal("1")):
        raise ValueError("calibration_score must be in [0,1]")
    if estimated_cost < 0 or safety_margin < 0 or base_risk < 0:
        raise ValueError("cost, safety margin and risk must be non-negative")

    side = "BUY" if forecast.expected_return > 0 else "SELL"
    probability = forecast.probability_up if side == "BUY" else Decimal("1") - forecast.probability_up
    edge = abs(forecast.expected_return) - estimated_cost - safety_margin
    market_block = market.event_state.value in {"IMMEDIATE_EVENT", "INTERVENTION_RISK", "BROKER_STRESS", "DATA_STRESS"}
    state = "ADMITTED"
    reason = "executable"
    if market_block:
        state, reason = "REJECTED", f"blocked_market_state:{market.event_state.value}"
    elif probability < min_probability:
        state, reason = "REJECTED", "probability_below_threshold"
    elif forecast.calibration_score < min_calibration:
        state, reason = "REJECTED", "calibration_below_threshold"
    elif edge < min_edge:
        state, reason = "REJECTED", "edge_below_threshold"
    elif market.liquidity_score < Decimal("0.55"):
        state, reason = "REJECTED", "liquidity_below_threshold"

    risk = base_risk if state == "ADMITTED" else Decimal("0")
    evidence_ids = tuple(sorted(set(forecast.evidence_ids)))
    stable = f"{instrument}|{side}|{forecast.model_id}|{forecast.version}|{forecast.generated_at_ms}|{edge}|{','.join(evidence_ids)}"
    candidate_id = "opp-" + sha256(stable.encode("utf-8")).hexdigest()[:24]
    return OpportunityCandidate(
        candidate_id=candidate_id,
        instrument=instrument,
        side=side,
        expected_return=abs(forecast.expected_return),
        probability=probability,
        calibration_score=forecast.calibration_score,
        estimated_cost=estimated_cost,
        safety_margin=safety_margin,
        executable_edge=edge,
        suggested_risk=risk,
        state=state,
        model_id=forecast.model_id,
        model_version=forecast.version,
        evidence_ids=evidence_ids,
        reason=reason,
    )


__all__ = ["OpportunityCandidate", "build_candidate"]
