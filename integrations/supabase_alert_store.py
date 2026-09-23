"""Server-side durable runtime alert sink with optional HTTPS webhook fan-out."""
from __future__ import annotations
import json, os, ssl, urllib.error, urllib.request
from datetime import datetime, timezone
from typing import Any, Mapping

class SupabaseAlertSink:
    def __init__(self, *, environment: str, timeout_seconds: float = 5.0, webhook_url: str | None = None):
        self.environment=environment.strip().lower()
        self.base_url=os.environ.get("SUPABASE_URL","").rstrip("/")
        self.api_key=os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY","")
        self.timeout_seconds=timeout_seconds
        self.webhook_url=webhook_url if webhook_url is not None else os.environ.get("AG_ALERT_WEBHOOK_URL","").strip()
        if not self.base_url or not self.api_key: raise RuntimeError("SUPABASE_URL and server-side Supabase key are required")
        if not self.base_url.startswith("https://"): raise RuntimeError("SUPABASE_URL must use https")
        if self.webhook_url and not self.webhook_url.startswith("https://"): raise ValueError("AG_ALERT_WEBHOOK_URL must use https")

    def emit(self, *, severity: str, source: str, alert_key: str, correlation_id: str, message: str, payload: Mapping[str, Any] | None=None) -> None:
        record={"environment":self.environment,"severity":severity,"source":source,"alert_key":alert_key,"correlation_id":correlation_id,
                "message":message,"payload":dict(payload or {})}
        endpoint=f"{self.base_url}/rest/v1/runtime_alerts"
        body=json.dumps(record,separators=(",",":"),default=str).encode()
        req=urllib.request.Request(endpoint,data=body,method="POST",headers={"apikey":self.api_key,"Authorization":f"Bearer {self.api_key}","Content-Type":"application/json","Accept":"application/json","Prefer":"return=minimal"})
        try:
            with urllib.request.urlopen(req,timeout=self.timeout_seconds,context=ssl.create_default_context()): pass
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Supabase runtime alert failed:{exc.code}") from exc
        if self.webhook_url:
            hook_body=json.dumps({**record,"created_at":datetime.now(timezone.utc).isoformat()},separators=(",",":"),default=str).encode()
            hook=urllib.request.Request(self.webhook_url,data=hook_body,method="POST",headers={"Content-Type":"application/json","Accept":"application/json","User-Agent":"AG-Demo-Trading-Alert/1"})
            try:
                with urllib.request.urlopen(hook,timeout=self.timeout_seconds,context=ssl.create_default_context()): pass
            except Exception:
                # Webhook is a secondary fan-out. Database persistence remains authoritative.
                pass

__all__=["SupabaseAlertSink"]
