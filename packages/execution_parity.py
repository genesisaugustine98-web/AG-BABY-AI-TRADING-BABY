"""Deterministic execution contract parity checks for demo/paper replay."""
from __future__ import annotations
import hashlib, json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from .models import AdmissionContext, InstrumentSpec, TradeIntent

@dataclass(frozen=True)
class ExecutionParityResult:
    compatible: bool
    demo_fingerprint: str
    paper_fingerprint: str
    reasons: tuple[str, ...]

def _normalize(value: Any) -> Any:
    if isinstance(value, Decimal): return str(value)
    if isinstance(value, (tuple, list)): return [_normalize(v) for v in value]
    if isinstance(value, dict): return {str(k): _normalize(v) for k,v in sorted(value.items(), key=lambda x:str(x[0]))}
    return value

def execution_contract_fingerprint(*, intent: TradeIntent, context: AdmissionContext, instrument: InstrumentSpec) -> str:
    payload = _normalize({"intent": {
        "symbol": intent.symbol, "side": intent.side, "quantity": intent.quantity, "order_type": intent.order_type,
        "limit_price": intent.limit_price, "stop_price": intent.stop_price, "target_price": intent.target_price,
        "expires_at_ms": intent.expires_at_ms, "max_slippage_fraction": intent.max_slippage_fraction,
        "risk_fraction": intent.risk_fraction, "horizon_seconds": intent.horizon_seconds},
        "context": {"quote": {"bid": context.quote.bid, "ask": context.quote.ask, "event_time_ms": context.quote.event_time_ms},
        "estimated_cost_fraction": context.estimated_cost_fraction, "safety_margin_fraction": context.safety_margin_fraction},
        "instrument": instrument.__dict__})
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def compare_execution_contracts(*, demo_intent: TradeIntent, demo_context: AdmissionContext, demo_instrument: InstrumentSpec,
                                paper_intent: TradeIntent, paper_context: AdmissionContext, paper_instrument: InstrumentSpec) -> ExecutionParityResult:
    left = execution_contract_fingerprint(intent=demo_intent, context=demo_context, instrument=demo_instrument)
    right = execution_contract_fingerprint(intent=paper_intent, context=paper_context, instrument=paper_instrument)
    return ExecutionParityResult(left == right, left, right, () if left == right else ("EXECUTION_CONTRACT_FINGERPRINT_MISMATCH",))
