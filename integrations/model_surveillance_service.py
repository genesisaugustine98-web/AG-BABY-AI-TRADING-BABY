"""Persistent model surveillance and retirement orchestration."""
from __future__ import annotations
from dataclasses import dataclass
from packages.model_monitoring import ModelSurveillanceDecision, ModelSurveillanceEngine
from integrations.supabase_model_registry import SupabaseModelRegistry
from integrations.supabase_alert_store import SupabaseAlertSink

@dataclass(frozen=True)
class ModelSurveillanceResult:
    decision: ModelSurveillanceDecision
    retired: bool

class ModelSurveillanceService:
    def __init__(self, *, registry: SupabaseModelRegistry, engine: ModelSurveillanceEngine, environment: str, alert_sink: SupabaseAlertSink | None=None):
        self.registry=registry; self.engine=engine; self.environment=environment
        self.alert_sink=alert_sink

    def observe(self, *, model_id: str, version: str, psi=None, brier_score=None, rolling_net_bps=None, drawdown_fraction=None) -> ModelSurveillanceResult:
        status = self.registry.get_status(model_id=model_id, version=version)
        if status == "retired":
            raise RuntimeError(f"model_already_retired:{model_id}:{version}")
        state = self.engine.state(model_id=model_id, version=version)
        if state.consecutive_breaches == 0:
            recent = self.registry.latest_surveillance(model_id=model_id, version=version, limit=1)
            if recent:
                row = recent[0]
                previous = int(row.get("breach_count") or 0)
                decision_name = str(row.get("decision") or "RETAIN")
                self.engine.seed_state(model_id=model_id, version=version, consecutive_breaches=previous, last_decision=decision_name)
        decision=self.engine.observe(model_id=model_id,version=version,psi=psi,brier_score_value=brier_score,rolling_net_bps=rolling_net_bps,drawdown_fraction=drawdown_fraction)
        self.registry.record_surveillance(model_id=model_id,version=version,decision=decision,environment=self.environment)
        retired=False
        if decision.decision=="RETIRE":
            self.registry.retire(model_id=model_id,version=version,reason=";".join(decision.reasons))
            retired=True
            if self.alert_sink:
                try:
                    self.alert_sink.emit(severity="CRITICAL",source="model_surveillance",alert_key="MODEL_RETIRED",
                        correlation_id=f"{model_id}:{version}",message="Model retired by configured surveillance policy",
                        payload={"model_id":model_id,"version":version,"breach_count":decision.breach_count,"reasons":list(decision.reasons)})
                except Exception: pass
        return ModelSurveillanceResult(decision,retired)

__all__=["ModelSurveillanceResult","ModelSurveillanceService"]
