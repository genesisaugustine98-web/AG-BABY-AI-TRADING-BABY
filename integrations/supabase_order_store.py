"""Trusted-server persistence for the internal order boundary.

Identity is always scoped by environment. Broker tickets are never accepted as a
substitute for internal order identity; a broker order can only bind to a durable
order created before submission.
"""
from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
import certifi
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

from apps.execution_gateway.mt5_fills import InternalOrderResolver
from packages.demo_execution import SubmissionRequest, SubmissionResult
from packages.models import TradeIntent


def _required(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty")
    return value.strip()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class DurableOrder:
    order_id: str
    environment: str
    intent_id: str
    client_order_id: str
    instrument: str
    side: str
    requested_quantity: Decimal
    order_type: str
    limit_price: Decimal | None
    state: str
    broker_order_id: str | None


class SupabaseOrderStore(InternalOrderResolver):
    def __init__(self, *, environment: str = "demo", timeout_seconds: float = 10.0) -> None:
        self.environment = _required(environment, "environment")
        self.timeout_seconds = timeout_seconds
        self.base_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        self.api_key = os.environ.get("SUPABASE_SECRET_KEY", "") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if not self.base_url or not self.api_key:
            raise RuntimeError("SUPABASE_URL and server-side Supabase key are required")
        if not self.base_url.startswith("https://"):
            raise RuntimeError("SUPABASE_URL must use https")

    def _request(self, method: str, table: str, *, query: Mapping[str, str] | None = None, body: Any = None, prefer: str | None = None) -> Any:
        qs = urllib.parse.urlencode(query or {}, safe="(),.*")
        url = f"{self.base_url}/rest/v1/{table}" + (f"?{qs}" if qs else "")
        data = None if body is None else json.dumps(body, separators=(",", ":"), default=str).encode("utf-8")
        headers = {"apikey": self.api_key, "Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if prefer:
            headers["Prefer"] = prefer
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers, method=method), timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Supabase {method} {table} failed HTTP {exc.code}: {detail[:400]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Supabase {method} {table} connection failed: {exc.reason}") from exc

    def ensure_intended(self, intent: TradeIntent, client_order_id: str) -> DurableOrder:
        client_order_id = _required(client_order_id, "client_order_id")
        rows = self._request(
            "GET",
            "execution_orders",
            query={
                "environment": f"eq.{self.environment}",
                "client_order_id": f"eq.{client_order_id}",
                "select": "order_id,environment,intent_id,client_order_id,instrument,side,requested_quantity,order_type,limit_price,state,broker_order_id",
            },
        ) or []
        if len(rows) > 1:
            raise RuntimeError(f"ambiguous_client_order_id:{client_order_id}")
        if rows:
            row = rows[0]
            if row.get("intent_id") and row.get("intent_id") != intent.intent_id:
                raise RuntimeError(f"client_order_id_intent_conflict:{client_order_id}")
            return self._row(row)

        order_id = f"ord-{client_order_id}"
        payload = {
            "order_id": order_id,
            "correlation_id": client_order_id,
            "intent_id": intent.intent_id,
            "environment": self.environment,
            "instrument": intent.symbol,
            "side": intent.side.lower(),
            "order_type": intent.order_type,
            "requested_quantity": str(intent.quantity),
            "limit_price": str(intent.limit_price) if intent.limit_price is not None else None,
            "state": "INTENDED",
            "client_order_id": client_order_id,
            "metadata": {
                "strategy_id": intent.strategy_id,
                "strategy_version": intent.strategy_version,
                "policy_version": intent.policy_version,
                "stop_price": str(intent.stop_price),
                "target_price": str(intent.target_price) if intent.target_price is not None else None,
                "created_at_ms": intent.created_at_ms,
                "expires_at_ms": intent.expires_at_ms,
                "max_slippage_fraction": str(intent.max_slippage_fraction),
                "risk_fraction": str(intent.risk_fraction),
                "horizon_seconds": intent.horizon_seconds,
                "evidence_ids": sorted(intent.evidence_ids),
            },
        }
        self._request("POST", "execution_orders", body=payload, prefer="return=minimal")
        return self.get(order_id)

    def get(self, order_id: str) -> DurableOrder:
        order_id = _required(order_id, "order_id")
        rows = self._request(
            "GET",
            "execution_orders",
            query={
                "environment": f"eq.{self.environment}",
                "order_id": f"eq.{order_id}",
                "select": "order_id,environment,intent_id,client_order_id,instrument,side,requested_quantity,order_type,limit_price,state,broker_order_id",
            },
        ) or []
        if len(rows) != 1:
            raise RuntimeError(f"order_not_unique:{order_id}")
        return self._row(rows[0])

    def _row(self, row: Mapping[str, Any]) -> DurableOrder:
        return DurableOrder(
            order_id=str(row["order_id"]),
            environment=str(row["environment"]),
            intent_id=str(row.get("intent_id") or ""),
            client_order_id=str(row["client_order_id"]),
            instrument=str(row["instrument"]),
            side=str(row["side"]).upper(),
            requested_quantity=Decimal(str(row["requested_quantity"])),
            order_type=str(row["order_type"]),
            limit_price=None if row.get("limit_price") is None else Decimal(str(row["limit_price"])),
            state=str(row["state"]),
            broker_order_id=None if row.get("broker_order_id") is None else str(row["broker_order_id"]),
        )

    def mark_submitting(self, order_id: str) -> DurableOrder:
        order_id = _required(order_id, "order_id")
        current = self.get(order_id)
        if current.state not in {"INTENDED", "SUBMITTED", "ACKNOWLEDGED", "PARTIALLY_FILLED", "UNKNOWN"}:
            return current
        self._request(
            "PATCH",
            "execution_orders",
            query={"environment": f"eq.{self.environment}", "order_id": f"eq.{order_id}"},
            body={"state": "SUBMITTED", "last_internal_update_at": _utc_now()},
            prefer="return=minimal",
        )
        return self.get(order_id)

    def record_submission(self, order_id: str, result: SubmissionResult) -> DurableOrder:
        current = self.get(order_id)
        if result.outcome == "UNKNOWN":
            body = {"state": "UNKNOWN", "last_internal_update_at": _utc_now()}
        elif result.outcome == "REJECTED":
            body = {"state": "REJECTED", "last_internal_update_at": _utc_now()}
        elif result.outcome == "ACCEPTED":
            body = {
                "state": "ACKNOWLEDGED",
                "broker_order_id": result.broker_order_id,
                "last_internal_update_at": _utc_now(),
                "last_broker_update_at": _utc_now(),
            }
        else:
            raise ValueError(f"unsupported broker submission outcome:{result.outcome}")
        # A broker ticket, once bound, cannot silently change.
        if current.broker_order_id and result.broker_order_id and current.broker_order_id != result.broker_order_id:
            raise RuntimeError(f"broker_order_id_conflict:{order_id}")
        self._request(
            "PATCH",
            "execution_orders",
            query={"environment": f"eq.{self.environment}", "order_id": f"eq.{order_id}"},
            body=body,
            prefer="return=minimal",
        )
        return self.get(order_id)

    def resolve(self, broker_order_id: str, instrument: str, side: str) -> str | None:
        broker_order_id = _required(broker_order_id, "broker_order_id")
        instrument = _required(instrument, "instrument")
        side = _required(side, "side").lower()
        rows = self._request(
            "GET",
            "execution_orders",
            query={
                "environment": f"eq.{self.environment}",
                "broker_order_id": f"eq.{broker_order_id}",
                "instrument": f"eq.{instrument}",
                "side": f"eq.{side}",
                "select": "order_id,client_order_id",
            },
        ) or []
        if len(rows) > 1:
            raise RuntimeError(f"ambiguous_broker_order_id:{self.environment}:{broker_order_id}")
        return str(rows[0]["order_id"]) if rows else None


__all__ = ["DurableOrder", "SupabaseOrderStore"]
