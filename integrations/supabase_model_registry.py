"""Server-side persistence for model lineage and governance evidence."""
from __future__ import annotations

import json
import os
import ssl
from datetime import datetime, timezone
import urllib.request
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping


class SupabaseModelRegistry:
    def __init__(self, *, timeout_seconds: float = 10.0) -> None:
        self.timeout_seconds = timeout_seconds
        self.base_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        self.api_key = os.environ.get("SUPABASE_SECRET_KEY", "") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if not self.base_url or not self.api_key:
            raise RuntimeError("SUPABASE_URL and server-side Supabase key are required")
        if not self.base_url.startswith("https://"):
            raise RuntimeError("SUPABASE_URL must use https")

    def record_validation(self, *, model_id: str, version: str, validation: Any, status: str, governance_state: str) -> None:
        if status not in {"candidate", "validated", "production", "retired", "blocked"}:
            raise ValueError(f"invalid registry status:{status}")
        payload = {
            "model_id": model_id,
            "version": version,
            "status": status,
            "dataset_fingerprint": str(validation.dataset_fingerprint),
            "code_commit_sha": str(validation.code_commit_sha),
            "artifact_uri": None,
            "metrics": self._jsonable(validation),
            "calibration": {
                "calibration_score": str(validation.calibration_score),
                "validation_ece": str(validation.validation_ece),
                "governance_state": governance_state,
            },
            "feature_version": str(validation.feature_fingerprint),
        }
        self._request("POST", "model_registry", payload, prefer="resolution=merge-duplicates,return=minimal")

    def get_status(self, *, model_id: str, version: str) -> str | None:
        rows = self._request("GET", "model_registry", query={
            "model_id": f"eq.{model_id}", "version": f"eq.{version}", "select": "status", "limit": "1"
        }) or []
        return str(rows[0]["status"]) if rows else None

    def record_surveillance(
        self,
        *,
        model_id: str,
        version: str,
        decision: Any,
        environment: str,
    ) -> None:
        self._request("POST", "model_surveillance_events", {
            "environment": environment,
            "model_id": model_id,
            "version": version,
            "decision": decision.decision,
            "breach_count": decision.breach_count,
            "psi": decision.psi,
            "brier_score": decision.brier_score,
            "rolling_net_bps": decision.rolling_net_bps,
            "drawdown_fraction": decision.drawdown_fraction,
            "reasons": list(decision.reasons),
            "metrics": {"decision": decision.decision},
        }, prefer="return=minimal")

    def retire(self, *, model_id: str, version: str, reason: str) -> None:
        status=self.get_status(model_id=model_id, version=version)
        if status == "retired": return
        if status is None: raise RuntimeError(f"model_not_registered:{model_id}:{version}")
        self._request(
            "PATCH", "model_registry",
            {"status": "retired", "retired_at": datetime.now(timezone.utc).isoformat()},
            query={"model_id": f"eq.{model_id}", "version": f"eq.{version}"},
            prefer="return=minimal",
        )

    def _request(self, method: str, table: str, body: Any = None, *, prefer: str | None = None) -> Any:
        url = f"{self.base_url}/rest/v1/{table}"
        data = None if body is None else json.dumps(body, separators=(",", ":"), default=str).encode()
        headers = {
            "apikey": self.api_key,
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        if prefer:
            headers["Prefer"] = prefer
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds, context=ssl.create_default_context()) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except Exception as exc:
            raise RuntimeError(f"Supabase model registry {method} failed") from exc

    @classmethod
    def _jsonable(cls, value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, Decimal):
            return str(value)
        if is_dataclass(value):
            return {key: cls._jsonable(item) for key, item in asdict(value).items()}
        if isinstance(value, Mapping):
            return {str(key): cls._jsonable(item) for key, item in value.items()}
        if isinstance(value, (tuple, list, set, frozenset)):
            return [cls._jsonable(item) for item in value]
        return value


__all__ = ["SupabaseModelRegistry"]
