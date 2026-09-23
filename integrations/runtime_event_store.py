"""Durable runtime-event persistence through the existing Supabase execution event ledger.

This adapter is server-only and intentionally treats the in-memory EventBus as the transport
and Supabase as the durable audit/replay source. It never receives broker credentials.
"""
from __future__ import annotations

import json
import os
import ssl
from threading import RLock
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
        self._chain_lock = RLock()
        self._last_event_hash: str | None = None
        if not self.base_url or not self.api_key:
            raise RuntimeError("SUPABASE_URL and server-side Supabase key are required")
        if not self.base_url.startswith("https://"):
            raise RuntimeError("SUPABASE_URL must use https")

    def append(self, event: RuntimeEvent) -> None:
        with self._chain_lock:
            if self._last_event_hash is None:
                rows = self._request(
                    "GET",
                    "execution_events",
                    query={
                        "environment": f"eq.{self.environment}",
                        "select": "event_hash",
                        "event_hash": "not.is.null",
                        "order": "occurred_at.desc,event_id.desc",
                        "limit": "1",
                    },
                ) or []
                self._last_event_hash = str(rows[0]["event_hash"]) if rows else None

            db_event_id = self._db_event_id(event.event_id)
            existing = self._request(
                "GET",
                "execution_events",
                query={
                    "event_id": f"eq.{db_event_id}",
                    "environment": f"eq.{self.environment}",
                    "select": "event_hash,previous_event_hash",
                    "limit": "1",
                },
            ) or []
            if existing:
                row = existing[0]
                previous_hash = row.get("previous_event_hash")
                expected = self._stable_hash(event, previous_hash)
                if str(row.get("event_hash") or "") != expected:
                    raise RuntimeError(f"runtime event id collision or tamper:{event.event_id}")
                return

            previous_hash = self._last_event_hash
            event_hash = self._stable_hash(event, previous_hash)
            payload = {
                "event_id": db_event_id,
                "occurred_at": datetime.fromtimestamp(event.occurred_at_ms / 1000, tz=timezone.utc).isoformat(),
                "environment": self.environment,
                "event_type": type(event).__name__,
                "correlation_id": self._correlation_id(event),
                "intent_id": getattr(event, "intent_id", None),
                "order_id": getattr(event, "order_id", None),
                "broker_order_id": getattr(event, "broker_order_id", None),
                "position_id": None,
                "payload": self._jsonable(event),
                "source": event.source,
                "source_version": event.source_version,
                "previous_event_hash": previous_hash,
                "event_hash": event_hash,
            }
            self._request("POST", "execution_events", payload)
            self._last_event_hash = event_hash

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
            "select": "event_id,occurred_at,event_type,correlation_id,order_id,broker_order_id,position_id,payload,source,source_version,previous_event_hash,event_hash",
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

    @staticmethod
    def _db_event_id(event_id: str) -> str:
        import uuid
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"ag-runtime-event:{event_id}"))

    @classmethod
    def _stable_hash(cls, event: RuntimeEvent, previous_event_hash: str | None = None) -> str:
        import hashlib
        canonical = json.dumps(
            {"previous_event_hash": previous_event_hash, "event": cls._jsonable(event)},
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    @classmethod
    def verify_chain(cls, events: tuple[dict[str, Any], ...], *, initial_previous_hash: str | None = None) -> tuple[bool, str | None]:
        """Verify persisted event hashes for an ordered event segment."""
        previous = initial_previous_hash
        for row in events:
            payload = row.get("payload") or {}
            event_hash = str(row.get("event_hash") or "")
            if not event_hash:
                return False, str(row.get("event_id") or "")
            canonical = json.dumps(
                {"previous_event_hash": previous, "event": payload},
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
            import hashlib
            expected = hashlib.sha256(canonical.encode()).hexdigest()
            if row.get("previous_event_hash") != previous or event_hash != expected:
                return False, str(row.get("event_id") or "")
            previous = event_hash
        return True, previous

    @staticmethod
    def _correlation_id(event: RuntimeEvent) -> str:
        return (
            str(getattr(event, "client_order_id", "") or "")
            or str(getattr(event, "candidate", None).candidate_id if getattr(event, "candidate", None) else "")
            or event.event_id
        )


def attach_runtime_event_store(bus, store: RuntimeEventStore):
    """Attach persistence as an observer; failures are recorded but do not freeze the node."""
    return bus.subscribe(None, store.append, critical=False)


def attach_runtime_event_store_critical(bus, store: RuntimeEventStore):
    """Attach the audit ledger as a fail-closed observer for autonomous execution."""
    return bus.subscribe(None, store.append, critical=True)


__all__ = ["RuntimeEventStore", "attach_runtime_event_store", "attach_runtime_event_store_critical"]
