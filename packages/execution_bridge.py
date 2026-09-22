"""Governed bridge from research opportunity evidence to a demo TradeIntent.

This module does not generate alpha and cannot bypass research governance. It requires:
- an explicitly admitted OpportunityCandidate;
- non-empty evidence provenance;
- a registered model in an allowed validation state;
- execution-grade promotion metadata for the current stage;
- a live broker quote snapshot and protective stop/target;
- a deterministic risk budget.

The result is a TradeIntent only. Broker submission remains exclusively inside
ExecutionKernel -> deterministic risk engine -> MT5 demo adapter.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from typing import Mapping

from .intelligence_mesh import ModelForecast
from .models import InstrumentSpec, TradeIntent
from .opportunity import OpportunityCandidate
from .risk import volume_step_is_valid


@dataclass(frozen=True)
class RegisteredModel:
    model_id: str
    version: str
    status: str
    dataset_fingerprint: str
    code_commit_sha: str
    calibration_score: Decimal
    execution_grade: bool
    feature_version: str

    def validate_for_execution(self, environment: str) -> tuple[bool, tuple[str, ...]]:
        environment = environment.strip().lower()
        reasons: list[str] = []
        if environment not in {"paper", "demo"}:
            reasons.append("UNSUPPORTED_EXECUTION_ENVIRONMENT")
        if self.status not in {"validated", "production"}:
            reasons.append("MODEL_NOT_VALIDATED_FOR_EXECUTION")
        if not self.dataset_fingerprint.strip():
            reasons.append("MODEL_DATASET_FINGERPRINT_MISSING")
        if not self.code_commit_sha.strip():
            reasons.append("MODEL_CODE_COMMIT_MISSING")
        if not (Decimal("0") <= self.calibration_score <= Decimal("1")):
            reasons.append("MODEL_CALIBRATION_INVALID")
        if not self.feature_version.strip():
            reasons.append("MODEL_FEATURE_VERSION_MISSING")
        if environment == "demo" and not self.execution_grade:
            reasons.append("MODEL_NOT_EXECUTION_GRADE")
        return (not reasons, tuple(reasons))


@dataclass(frozen=True)
class BridgeResult:
    approved: bool
    reasons: tuple[str, ...]
    intent: TradeIntent | None


class GovernedExecutionBridge:
    """Turn independently validated research output into a deterministic intent."""

    def __init__(self, *, policy_version: str = "policy-v1", environment: str = "demo") -> None:
        self.policy_version = policy_version.strip()
        self.environment = environment.strip().lower()
        if not self.policy_version:
            raise ValueError("policy_version must be non-empty")
        if self.environment not in {"paper", "demo"}:
            raise ValueError("execution bridge supports paper or demo only")

    def build_intent(
        self,
        *,
        strategy_id: str,
        candidate: OpportunityCandidate,
        forecast: ModelForecast,
        registered_model: RegisteredModel,
        instrument: InstrumentSpec,
        quantity: Decimal,
        stop_price: Decimal,
        target_price: Decimal | None,
        now_ms: int,
        expires_at_ms: int,
        max_slippage_fraction: Decimal,
        horizon_seconds: int,
    ) -> BridgeResult:
        reasons: list[str] = []
        strategy_id = strategy_id.strip()
        if not strategy_id:
            reasons.append("STRATEGY_ID_REQUIRED")

        if candidate.state != "ADMITTED":
            reasons.append("OPPORTUNITY_NOT_ADMITTED")
        if candidate.instrument != instrument.symbol:
            reasons.append("INSTRUMENT_MISMATCH")
        if not candidate.evidence_ids:
            reasons.append("EVIDENCE_PROVENANCE_REQUIRED")
        if candidate.model_id != forecast.model_id or candidate.model_version != forecast.version:
            reasons.append("FORECAST_MODEL_ID_MISMATCH")
        if forecast.model_id != registered_model.model_id or forecast.version != registered_model.version:
            reasons.append("UNREGISTERED_FORECAST_VERSION")
        _, model_reasons = registered_model.validate_for_execution(self.environment)
        reasons.extend(model_reasons)
        if forecast.calibration_score != registered_model.calibration_score:
            reasons.append("FORECAST_CALIBRATION_MISMATCH")
        if quantity < instrument.min_volume or quantity > instrument.max_volume:
            reasons.append("BROKER_VOLUME_BOUNDS")
        if not volume_step_is_valid(quantity, instrument.min_volume, instrument.max_volume, instrument.volume_step):
            reasons.append("BROKER_VOLUME_STEP")
        if stop_price <= 0:
            reasons.append("INVALID_STOP")
        if target_price is not None and target_price <= 0:
            reasons.append("INVALID_TARGET")
        if expires_at_ms <= now_ms:
            reasons.append("INVALID_EXPIRY")
        if max_slippage_fraction < 0:
            reasons.append("INVALID_SLIPPAGE")
        if horizon_seconds < 1:
            reasons.append("INVALID_HORIZON")
        if forecast.generated_at.timestamp() * 1000 > now_ms:
            reasons.append("FUTURE_FORECAST_TIMESTAMP")
        if candidate.expected_return != abs(forecast.expected_return):
            reasons.append("FORECAST_RETURN_MISMATCH")
        if candidate.probability != (forecast.probability_up if candidate.side == "BUY" else Decimal("1") - forecast.probability_up):
            reasons.append("FORECAST_PROBABILITY_MISMATCH")
        if candidate.calibration_score != forecast.calibration_score:
            reasons.append("CANDIDATE_CALIBRATION_MISMATCH")
        if candidate.executable_edge <= 0:
            reasons.append("NON_POSITIVE_EXECUTABLE_EDGE")

        if reasons:
            return BridgeResult(False, tuple(dict.fromkeys(reasons)), None)

        intent_id_source = "|".join(
            [
                candidate.candidate_id,
                registered_model.model_id,
                registered_model.version,
                instrument.symbol,
                candidate.side,
                str(quantity),
                str(stop_price),
                str(target_price),
                str(now_ms),
            ]
        )
        intent_id = "intent-" + sha256(intent_id_source.encode("utf-8")).hexdigest()[:24]

        return BridgeResult(
            True,
            (),
            TradeIntent(
                intent_id=intent_id,
                strategy_id=strategy_id,
                strategy_version=candidate.model_version,
                policy_version=self.policy_version,
                symbol=instrument.symbol,
                side=candidate.side,
                quantity=quantity,
                order_type="MARKET",
                limit_price=None,
                stop_price=stop_price,
                target_price=target_price,
                created_at_ms=now_ms,
                expires_at_ms=expires_at_ms,
                max_slippage_fraction=max_slippage_fraction,
                risk_fraction=candidate.suggested_risk,
                horizon_seconds=horizon_seconds,
                evidence_ids=frozenset(candidate.evidence_ids),
            ),
        )


__all__ = ["BridgeResult", "GovernedExecutionBridge", "RegisteredModel"]
