"""Central event-to-alert routing for runtime safety signals."""
from __future__ import annotations
import hashlib
from dataclasses import dataclass
from typing import Any, Callable
from packages.events import FreezeEvent, HeartbeatEvent, OrderLifecycleEvent, ReconciliationEvent, RuntimeEvent

@dataclass(frozen=True)
class AlertSpec:
    severity: str
    alert_key: str
    message: str
    correlation_id: str
    payload: dict[str, Any]

class RuntimeAlertRouter:
    def __init__(self, sink: Callable[..., None]):
        self.sink=sink
    def inspect(self, event: RuntimeEvent) -> AlertSpec | None:
        correlation=str(getattr(event,"client_order_id","") or getattr(event,"correlation_id","") or event.event_id)
        if isinstance(event, FreezeEvent):
            return AlertSpec("CRITICAL","RUNTIME_FREEZE",event.reason,correlation,{"event_type":type(event).__name__,"reason":event.reason})
        if isinstance(event, OrderLifecycleEvent):
            outcome=(event.outcome or "").upper()
            if outcome=="UNKNOWN":
                return AlertSpec("CRITICAL","EXECUTION_UNKNOWN","Execution outcome entered UNKNOWN",correlation,{"order_id":event.order_id,"broker_order_id":event.broker_order_id,"reasons":list(event.reasons)})
            if outcome=="REJECTED":
                key="EXECUTION_REJECTED:"+hashlib.sha256("|".join(event.reasons).encode()).hexdigest()[:12]
                return AlertSpec("WARN",key,"Broker rejected an execution request",correlation,{"order_id":event.order_id,"reasons":list(event.reasons)})
        if isinstance(event, ReconciliationEvent) and (event.frozen or str(event.status).upper()!="MATCHED"):
            return AlertSpec("CRITICAL","RECONCILIATION_NOT_CLEAN","Broker reconciliation did not establish clean truth",correlation,{"status":event.status,"frozen":event.frozen,"reasons":list(event.reasons)})
        if isinstance(event, HeartbeatEvent) and str(event.health).upper() not in {"HEALTHY","OK","RUNNING"}:
            return AlertSpec("ERROR","RUNTIME_HEALTH_DEGRADED","Runtime heartbeat reports degraded health",correlation,{"state":event.state,"health":event.health})
        return None
    def observe(self, event: RuntimeEvent) -> None:
        spec=self.inspect(event)
        if spec is not None:
            self.sink(severity=spec.severity,source=event.source,alert_key=spec.alert_key,correlation_id=spec.correlation_id,message=spec.message,payload=spec.payload)

__all__=["AlertSpec","RuntimeAlertRouter"]
