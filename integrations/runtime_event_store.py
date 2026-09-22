"""Durable runtime-event persistence through the existing Supabase execution event ledger.

This adapter is server-only and intentionally treats the in-memory EventBus as the transport
and Supabase as the durable audit/replay source. It never receives broker credentials.
"""
from __future__ import annotations

import json
import os
import ssl
import urllib.parse
import urllib.request
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from packages.events import RuntimeEvent


class RuntimeEventStore:
    def __init__(self, *, environment: str, timeout_seconds: float = 10.0) -> None:
        environment = environment.strip().lower()
        if environment not in {"research", "paper", "demo"}:
            raise ValueError("runtime event store environment must be research, paper or demo")
        self.environment = environment
        self.timeout_seconds = timeout_seconds
        self.base_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        self.api_key = os.environ.get("SUPABASE_SECRET_KEY", "") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if not self.base_url or not self.api_key:
            raise RuntimeError("SUPABASE_URL and server-side Supabase key are required")
        if not self.base_url.startswith("https://"):
            raise RuntimeError("SUPABASE_URL must use https")

    def append(self, event: RuntimeEvent) -> None:
        payload = {
            "event_id": event.event_id,
            "occurred_at": datetime.fromtimestamp(event.occurred_at_ms / 1000, tz=timezone.utc).isoformat(),
            "environment": self.environment,
            "event_type": type(event).__name__,
            "correlation_id": self._correlation_id(event),
            "order_id": getattr(event, "order_id", None),
            "broker_order_id": getattr(event, "broker_order_id", None),
            "position_id": getattr(event, "symbol", None),
            "payload": self._jsonable(event),
            "source": event.source,
            "source_version": event.source_version,
            "previous_event_hash": None,
            "event_hash": self._stable_hash(event),
        }
        self._request("POST", "execution_events", payload)

    def replay(
        self,
        *,
        event_type: str | None = None,
        correlation_id: str | None = None,
        limit: int = 500,
    ) -> tuple[dict[str, Any], ...]:
        if limit < 1 or limit > 5_000:
            raise ValueError("limit must be between 1 and 5000")
        query = {
            "environment": f"eq.{self.environment}",
            "select": "event_id,occurred_at,event_type,correlation_id,order_id,broker_order_id,position_id,payload,source,source_version,event_hash",
            "order": "occurred_at.asc",
            "limit": str(limit),
        }
        if event_type:
            query["event_type"] = f"eq.{event_type}"
        if correlation_id:
            query["correlation_id"] = f"eq.{correlation_id}"
        result = self._request("GET", "execution_events", query=query)
        return tuple(result or ())

    def _request(self, method: str, table: str, body: Any = None, *, query: dict[str, str] | None = None) -> Any:
        qs = urllib.parse.urlencode(query or {}, safe="(),.*")
        url = f"{self.base_url}/rest/v1/{table}" + (f"?{qs}" if qs else "")
        data = None if body is None else json.dumps(body, separators=(",", ":"), default=str).encode()
        headers = {
            "apikey": self.api_key,
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
            headers["Prefer"] = "resolution=ignore-duplicates,return=minimal"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds, context=ssl.create_default_context()) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except Exception as exc:
            raise RuntimeError(f"Supabase runtime event {method} {table} failed") from exc

    @classmethod
    def _jsonable(cls, value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        if is_dataclass(value):
            return {key: cls._jsonable(item) for key, item in asdict(value).items()}
        if isinstance(value, dict):
            return {str(key): cls._jsonable(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set, frozenset)):
            return [cls._jsonable(item) for item in value]
        return value

    @classmethod
    def _stable_hash(cls, event: RuntimeEvent) -> str:
        import hashlib
        canonical = json.dumps(cls._jsonable(event), sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def _correlation_id(event: RuntimeEvent) -> str:
        return (
            str(getattr(event, "client_order_id", "") or "")
            or str(getattr(event, "candidate", None).candidate_id if getattr(event, "candidate", None) else "")
            or event.event_id
        )


def attach_runtime_event_store(bus, store: RuntimeEventStore):
    """Attach persistence as a non-critical EventBus observer."""
    return bus.subscribe(None, store.append, critical=False)


__all__ = ["RuntimeEventStore", "attach_runtime_event_store"]
