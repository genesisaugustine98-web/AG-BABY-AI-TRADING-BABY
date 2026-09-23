"""Server-only durable execution persistence backed by Supabase PostgREST.

This adapter is intentionally small and dependency-free. It must run only in a trusted
backend/worker process with SUPABASE_SERVICE_ROLE_KEY; never expose that key to a browser.
The database remains authoritative for restart-safe safety state.
"""
from __future__ import annotations

import json
import os
import ssl
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

from packages.broker_truth import BrokerPositionTruth, BrokerSnapshot, ReconciliationOutcome
from packages.execution_ledger import InternalOrderTruth


_TERMINAL_ORDER_STATES = {"FILLED", "REJECTED", "CANCELED", "CANCELLED"}


class SupabaseExecutionStore:
    def __init__(self, *, environment: str = "demo", timeout_seconds: float = 10.0) -> None:
        self.environment = environment.strip().lower()
        if self.environment not in {"demo", "paper", "live"}:
            raise ValueError("invalid execution environment")
        self.timeout_seconds = timeout_seconds
        self.base_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        self.api_key = os.environ.get("SUPABASE_SECRET_KEY", "") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if not self.base_url or not self.api_key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required server-side")
        if not self.base_url.startswith("https://"):
            raise RuntimeError("SUPABASE_URL must use https")

    def _request(self, method: str, table: str, *, query: dict[str, str] | None = None,
                 body: Any | None = None, prefer: str | None = None) -> Any:
        qs = urllib.parse.urlencode(query or {}, safe="(),.*")
        url = f"{self.base_url}/rest/v1/{table}" + (f"?{qs}" if qs else "")
        data = None if body is None else json.dumps(body, separators=(",", ":"), default=str).encode()
        headers = {"apikey": self.api_key, "Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
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
            raise RuntimeError(f"Supabase {method} {table} request failed") from exc

    @staticmethod
    def _decimal(value: Any) -> Decimal:
        return Decimal(str(value))

    def active_orders(self) -> tuple[InternalOrderTruth, ...]:
        rows = self._request("GET", "execution_orders", query={
            "select": "order_id,client_order_id,instrument,state,filled_quantity",
            "environment": f"eq.{self.environment}",
            "state": "not.in.(FILLED,REJECTED,CANCELLED,CANCELED)",
            "is_test_fixture": "eq.false",
            "order_id": "not.is.null",
        }) or []
        return tuple(
            InternalOrderTruth(str(row["order_id"]), str(row.get("client_order_id") or ""), str(row["instrument"]), str(row["state"]), self._decimal(row.get("filled_quantity", "0")))
            for row in rows
            if str(row.get("state")) not in _TERMINAL_ORDER_STATES
        )

    def positions(self) -> tuple[BrokerPositionTruth, ...]:
        rows = self._request("GET", "execution_positions", query={
            "select": "instrument,net_quantity", "environment": f"eq.{self.environment}", "is_test_fixture": "eq.false"
        }) or []
        return tuple(BrokerPositionTruth(str(row["instrument"]), self._decimal(row["net_quantity"])) for row in rows)

    def record_account_snapshot(self, account: Mapping[str, Any]) -> None:
        """Persist one normalized broker account snapshot without ever persisting secrets."""
        captured_at = str(account.get("captured_at") or datetime.now(timezone.utc).isoformat())
        payload = {
            "snapshot_id": str(account.get("snapshot_id") or uuid.uuid4()),
            "environment": self.environment,
            "captured_at": captured_at,
            "broker": str(account.get("broker") or "mt5"),
            "account_login": None if account.get("login") is None else str(account.get("login")),
            "server": None if account.get("server") is None else str(account.get("server")),
            "currency": None if account.get("currency") is None else str(account.get("currency")),
            "balance": str(account.get("balance", 0)),
            "equity": str(account.get("equity", 0)),
            "margin": None if account.get("margin") is None else str(account.get("margin")),
            "margin_free": None if account.get("margin_free") is None else str(account.get("margin_free")),
            "margin_level": None if account.get("margin_level") is None else str(account.get("margin_level")),
            "trade_allowed": account.get("trade_allowed"),
            "payload": {k: v for k, v in account.items() if k.lower() not in {"password", "api_key", "secret", "token"}},
        }
        self._request("POST", "execution_account_snapshots", body=payload, prefer="return=minimal")

    def record_snapshot(self, snapshot: BrokerSnapshot) -> None:
        """Persist broker truth through the same tamper-evident runtime-event ledger."""
        from integrations.runtime_event_store import RuntimeEventStore
        from datetime import datetime, timezone

        occurred_at_ms = int(datetime.fromisoformat(snapshot.captured_at.replace("Z", "+00:00")).timestamp() * 1000)
        RuntimeEventStore(environment=self.environment, timeout_seconds=self.timeout_seconds).append_record(
            event_id=self._event_id("broker_snapshot", snapshot.captured_at),
            occurred_at_ms=occurred_at_ms,
            event_type="BROKER_SNAPSHOT",
            correlation_id=f"{self.environment}:broker_snapshot",
            payload={
                "orders": [
                    {
                        "broker_order_id": o.broker_order_id,
                        "client_order_id": o.client_order_id,
                        "instrument": o.instrument,
                        "state": o.state,
                        "filled_quantity": str(o.filled_quantity),
                    }
                    for o in snapshot.orders
                ],
                "positions": [
                    {"instrument": p.instrument, "net_quantity": str(p.net_quantity)}
                    for p in snapshot.positions
                ],
                "captured_at": snapshot.captured_at,
            },
            source="broker_truth_adapter",
            source_version="broker-snapshot-v3",
        )

    def record_outcome(self, outcome: ReconciliationOutcome) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._request("POST", "execution_reconciliations", body={
            "started_at": now,
            "completed_at": now,
            "environment": self.environment,
            "broker": "mt5",
            "status": outcome.status,
            "orders_checked": len(outcome.results),
            "fills_checked": 0,
            "positions_checked": len(outcome.results),
            "drift_count": sum(r.drift_count for r in outcome.results) + len(outcome.position_drift),
            "details": {
                "results": [{"status": r.status, "drift_count": r.drift_count, "reasons": list(r.reasons)} for r in outcome.results],
                "position_drift": list(outcome.position_drift),
            },
        }, prefer="return=minimal")

    def load_frozen(self) -> bool:
        rows = self._request("GET", "execution_control_state", query={"select": "frozen", "environment": f"eq.{self.environment}", "limit": "1"}) or []
        return bool(rows[0]["frozen"]) if rows else True

    def set_frozen(self, frozen: bool, reason: str | None = None) -> None:
        self._request("POST", "execution_control_state", body={"environment": self.environment, "frozen": bool(frozen), "reason": reason}, prefer="resolution=merge-duplicates,return=minimal")

    @staticmethod
    def _stable_hash(payload: Any) -> str:
        import hashlib
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()

    @classmethod
    def _event_id(cls, event_type: str, captured_at: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"ag-execution:{event_type}:{captured_at}"))
