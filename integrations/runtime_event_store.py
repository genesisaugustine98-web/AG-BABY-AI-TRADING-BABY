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
        self._alert_router = None
        if os.environ.get("AG_ALERTS_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}:
            try:
                from integrations.supabase_alert_store import SupabaseAlertSink
                from packages.observability import RuntimeAlertRouter
                sink = SupabaseAlertSink(environment=self.environment, timeout_seconds=min(timeout_seconds, 5.0))
                self._alert_router = RuntimeAlertRouter(sink.emit)
            except Exception:
                self._alert_router = None
        if not self.base_url or not self.api_key:
            raise RuntimeError("SUPABASE_URL and server-side Supabase key are required")
        if not self.base_url.startswith("https://"):
            raise RuntimeError("SUPABASE_URL must use https")

    def append(self, event: RuntimeEvent) -> None:
        self.append_record(
            event_id=event.event_id,
            occurred_at_ms=event.occurred_at_ms,
            event_type=type(event).__name__,
            correlation_id=self._correlation_id(event),
            intent_id=getattr(event, "intent_id", None),
            order_id=getattr(event, "order_id", None),
            broker_order_id=getattr(event, "broker_order_id", None),
            position_id=None,
            payload=self._jsonable(event),
            source=event.source,
            source_version=event.source_version,
        )

    def append_record(
        self,
        *,
        event_id: str,
        occurred_at_ms: int,
        event_type: str,
        correlation_id: str,
        payload: Any,
        source: str,
        source_version: str,
        intent_id: str | None = None,
        order_id: str | None = None,
        broker_order_id: str | None = None,
        position_id: str | None = None,
    ) -> None:
        if not event_id.strip() or occurred_at_ms <= 0 or not event_type.strip() or not correlation_id.strip():
            raise ValueError("event identity and occurrence metadata are required")
        if not source.strip() or not source_version.strip():
            raise ValueError("event provenance is required")

        with self._chain_lock:
            if self._last_event_hash is None:
                rows = self._request(
                    "GET",
                    "execution_events",
                    query={
                        "environment": f"eq.{self.environment}",
                        "select": "event_hash",
                        "event_hash": "not.is.null",
                        "order": "created_at.desc,event_id.desc",
                        "limit": "1",
                    },
                ) or []
                self._last_event_hash = str(rows[0]["event_hash"]) if rows else None

            db_event_id = self._db_event_id(event_id)
            existing = self._request(
                "GET",
                "execution_events",
                query={
                    "event_id": f"eq.{db_event_id}",
                    "environment": f"eq.{self.environment}",
                    "select": "event_hash,previous_event_hash,event_type,correlation_id,intent_id,order_id,broker_order_id,position_id,payload,source,source_version,occurred_at",
                    "limit": "1",
                },
            ) or []
            if existing:
                row = existing[0]
                previous_hash = row.get("previous_event_hash")
                expected = self._stable_record_hash(
                    event_id=db_event_id,
                    occurred_at=str(row.get("occurred_at") or ""),
                    environment=self.environment,
                    event_type=str(row.get("event_type") or ""),
                    correlation_id=str(row.get("correlation_id") or ""),
                    intent_id=row.get("intent_id"),
                    order_id=row.get("order_id"),
                    broker_order_id=row.get("broker_order_id"),
                    position_id=row.get("position_id"),
                    payload=row.get("payload") or {},
                    source=str(row.get("source") or ""),
                    source_version=str(row.get("source_version") or ""),
                    previous_event_hash=previous_hash,
                )
                if str(row.get("event_hash") or "") != expected:
                    raise RuntimeError(f"runtime event id collision or tamper:{event_id}")
                return

            occurred_at = datetime.fromtimestamp(occurred_at_ms / 1000, tz=timezone.utc).isoformat()
            previous_hash = self._last_event_hash
            db_event_id = self._db_event_id(event_id)
            event_hash = self._stable_record_hash(
                event_id=db_event_id,
                occurred_at=occurred_at,
                environment=self.environment,
                event_type=event_type,
                correlation_id=correlation_id,
                intent_id=intent_id,
                order_id=order_id,
                broker_order_id=broker_order_id,
                position_id=position_id,
                payload=self._jsonable(payload),
                source=source,
                source_version=source_version,
                previous_event_hash=previous_hash,
            )
            row = {
                "event_id": db_event_id,
                "occurred_at": occurred_at,
                "environment": self.environment,
                "event_type": event_type,
                "correlation_id": correlation_id,
                "intent_id": intent_id,
                "order_id": order_id,
                "broker_order_id": broker_order_id,
                "position_id": position_id,
                "payload": self._jsonable(payload),
                "source": source,
                "source_version": source_version,
                "previous_event_hash": previous_hash,
                "event_hash": event_hash,
            }
            self._request("POST", "execution_events", row)
            self._last_event_hash = event_hash
            if self._alert_router is not None:
                try:
                    self._alert_router.observe(event)
                except Exception:
                    pass

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
            "select": "event_id,occurred_at,environment,event_type,correlation_id,intent_id,order_id,broker_order_id,position_id,payload,source,source_version,previous_event_hash,event_hash",
            "order": "created_at.asc,event_id.asc",
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
    def _stable_record_hash(
        cls,
        *,
        event_id: str,
        occurred_at: str,
        environment: str,
        event_type: str,
        correlation_id: str,
        intent_id: str | None,
        order_id: str | None,
        broker_order_id: str | None,
        position_id: str | None,
        payload: Any,
        source: str,
        source_version: str,
        previous_event_hash: str | None,
    ) -> str:
        import hashlib
        canonical = json.dumps(
            {
                "event_id": event_id,
                "occurred_at": occurred_at,
                "environment": environment,
                "event_type": event_type,
                "correlation_id": correlation_id,
                "intent_id": intent_id,
                "order_id": order_id,
                "broker_order_id": broker_order_id,
                "position_id": position_id,
                "payload": payload,
                "source": source,
                "source_version": source_version,
                "previous_event_hash": previous_event_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    @classmethod
    def _stable_hash(cls, event: RuntimeEvent, previous_event_hash: str | None = None) -> str:
        return cls._stable_record_hash(
            event_id=cls._db_event_id(event.event_id),
            occurred_at=datetime.fromtimestamp(event.occurred_at_ms / 1000, tz=timezone.utc).isoformat(),
            environment="runtime",
            event_type=type(event).__name__,
            correlation_id=cls._correlation_id(event),
            intent_id=getattr(event, "intent_id", None),
            order_id=getattr(event, "order_id", None),
            broker_order_id=getattr(event, "broker_order_id", None),
            position_id=None,
            payload=cls._jsonable(event),
            source=event.source,
            source_version=event.source_version,
            previous_event_hash=previous_event_hash,
        )

    @classmethod
    def verify_chain(
        cls,
        events: tuple[dict[str, Any], ...],
        *,
        initial_previous_hash: str | None = None,
    ) -> tuple[bool, str | None]:
        """Verify the full persisted event envelope for an ordered event segment."""
        previous = initial_previous_hash
        for row in events:
            event_hash = str(row.get("event_hash") or "")
            if not event_hash:
                return False, str(row.get("event_id") or "")
            expected = cls._stable_record_hash(
                event_id=str(row.get("event_id") or ""),
                occurred_at=str(row.get("occurred_at") or ""),
                environment=str(row.get("environment") or ""),
                event_type=str(row.get("event_type") or ""),
                correlation_id=str(row.get("correlation_id") or ""),
                intent_id=row.get("intent_id"),
                order_id=row.get("order_id"),
                broker_order_id=row.get("broker_order_id"),
                position_id=row.get("position_id"),
                payload=row.get("payload") or {},
                source=str(row.get("source") or ""),
                source_version=str(row.get("source_version") or ""),
                previous_event_hash=previous,
            )
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
