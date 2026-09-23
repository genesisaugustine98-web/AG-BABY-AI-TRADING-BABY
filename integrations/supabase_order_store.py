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
    metadata: Mapping[str, Any] | None = None


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
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers, method=method), timeout=self.timeout_seconds, context=ssl.create_default_context()) as response:
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
                "is_test_fixture": "eq.false",
                "client_order_id": f"eq.{client_order_id}",
                "select": "order_id,environment,intent_id,client_order_id,instrument,side,requested_quantity,order_type,limit_price,state,broker_order_id,metadata",
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

    def active_order_risk_reservations(self) -> tuple[tuple[str, str, Decimal], ...]:
        """Return nonterminal durable order risk reservations for restart recovery."""
        rows = self._request(
            "GET",
            "execution_orders",
            query={
                "environment": f"eq.{self.environment}",
                "is_test_fixture": "eq.false",
                "state": "not.in.(FILLED,REJECTED,CANCELLED,CANCELED)",
                "select": "order_id,metadata",
            },
        ) or []
        reservations: list[tuple[str, str, Decimal]] = []
        for row in rows:
            metadata = row.get("metadata") or {}
            if not isinstance(metadata, Mapping):
                continue
            raw = metadata.get("risk_fraction")
            strategy_id = str(metadata.get("strategy_id") or "").strip()
            if raw is None or not strategy_id:
                continue
            risk = Decimal(str(raw))
            if not risk.is_finite() or risk < 0 or risk > Decimal("1"):
                raise RuntimeError(f"invalid durable risk reservation:{row.get('order_id')}")
            reservations.append((str(row["order_id"]), strategy_id, risk))
        return tuple(reservations)

    def get(self, order_id: str) -> DurableOrder:
        order_id = _required(order_id, "order_id")
        rows = self._request(
            "GET",
            "execution_orders",
            query={
                "environment": f"eq.{self.environment}",
                "order_id": f"eq.{order_id}",
                "select": "order_id,environment,intent_id,client_order_id,instrument,side,requested_quantity,order_type,limit_price,state,broker_order_id,metadata",
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
            metadata=dict(row.get("metadata") or {}),
        )

    @staticmethod
    def _merge_metadata(current: Mapping[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
        merged = dict(current)
        merged.update({str(k): v for k, v in patch.items()})
        return merged

    def record_execution_observation(self, order_id: str, observation: Mapping[str, Any]) -> DurableOrder:
        current = self.get(order_id)
        metadata = self._merge_metadata(current.metadata or {}, {"execution_observation": dict(observation)})
        self._request(
            "PATCH",
            "execution_orders",
            query={"environment": f"eq.{self.environment}", "order_id": f"eq.{order_id}"},
            body={"metadata": metadata, "last_internal_update_at": _utc_now()},
            prefer="return=minimal",
        )
        return self.get(order_id)

    def mark_replace_requested(
        self,
        order_id: str,
        limit_price: Decimal,
        stop_price: Decimal | None,
        target_price: Decimal | None,
        expires_at_ms: int,
    ) -> DurableOrder:
        current = self.get(order_id)
        if current.state not in {"ACKNOWLEDGED", "PARTIALLY_FILLED"}:
            raise RuntimeError(f"order_not_replaceable:{order_id}:{current.state}")
        metadata = self._merge_metadata(
            current.metadata or {},
            {
                "last_control": "REPLACE_REQUESTED",
                "replacement_limit_price": str(limit_price),
                "replacement_stop_price": None if stop_price is None else str(stop_price),
                "replacement_target_price": None if target_price is None else str(target_price),
                "replacement_expires_at_ms": int(expires_at_ms),
            },
        )
        self._request(
            "PATCH", "execution_orders",
            query={"environment": f"eq.{self.environment}", "order_id": f"eq.{order_id}"},
            body={"metadata": metadata, "last_internal_update_at": _utc_now()},
            prefer="return=minimal",
        )
        return self.get(order_id)

    def record_replacement(self, order_id: str, result: SubmissionResult) -> DurableOrder:
        current = self.get(order_id)
        metadata = self._merge_metadata(current.metadata or {}, {"last_control": "REPLACE_CONFIRMED" if result.outcome == "ACCEPTED" else "REPLACE_UNKNOWN"})
        body: dict[str, Any] = {"metadata": metadata, "last_internal_update_at": _utc_now()}
        if result.outcome == "UNKNOWN":
            body["state"] = "UNKNOWN"
        elif result.outcome == "REJECTED":
            body["state"] = current.state
        elif result.outcome == "ACCEPTED":
            raw_price = metadata.get("replacement_limit_price")
            if raw_price is not None:
                body["limit_price"] = str(raw_price)
        else:
            raise ValueError(f"unsupported replacement outcome:{result.outcome}")
        self._request("PATCH", "execution_orders", query={"environment": f"eq.{self.environment}", "order_id": f"eq.{order_id}"}, body=body, prefer="return=minimal")
        return self.get(order_id)

    def mark_expire_requested(self, order_id: str) -> DurableOrder:
        current = self.mark_cancel_requested(order_id)
        metadata = self._merge_metadata(current.metadata or {}, {"last_control": "EXPIRE_REQUESTED"})
        self._request(
            "PATCH", "execution_orders",
            query={"environment": f"eq.{self.environment}", "order_id": f"eq.{order_id}"},
            body={"metadata": metadata, "last_internal_update_at": _utc_now()},
            prefer="return=minimal",
        )
        return self.get(order_id)

    def record_expiration(self, order_id: str, result: SubmissionResult) -> DurableOrder:
        current = self.get(order_id)
        metadata = self._merge_metadata(current.metadata or {}, {"last_control": "EXPIRED" if result.outcome == "ACCEPTED" else "EXPIRE_UNKNOWN"})
        if result.outcome == "ACCEPTED":
            body = {"state": "CANCELLED", "metadata": metadata, "last_internal_update_at": _utc_now()}
        elif result.outcome in {"REJECTED", "UNKNOWN"}:
            body = {"state": "UNKNOWN", "metadata": metadata, "last_internal_update_at": _utc_now()}
        else:
            raise ValueError(f"unsupported expiration outcome:{result.outcome}")
        self._request("PATCH", "execution_orders", query={"environment": f"eq.{self.environment}", "order_id": f"eq.{order_id}"}, body=body, prefer="return=minimal")
        return self.get(order_id)

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

    def mark_cancel_requested(self, order_id: str) -> DurableOrder:
        order_id = _required(order_id, "order_id")
        current = self.get(order_id)
        if current.state not in {"SUBMITTED", "ACKNOWLEDGED", "PARTIALLY_FILLED"}:
            raise RuntimeError(f"order_not_cancelable:{order_id}:{current.state}")
        self._request(
            "PATCH",
            "execution_orders",
            query={"environment": f"eq.{self.environment}", "order_id": f"eq.{order_id}"},
            body={"state": "CANCEL_REQUESTED", "last_internal_update_at": _utc_now()},
            prefer="return=minimal",
        )
        return self.get(order_id)

    def record_cancellation(self, order_id: str, result: SubmissionResult) -> DurableOrder:
        order_id = _required(order_id, "order_id")
        if result.outcome == "ACCEPTED":
            state = "CANCELLED"
        elif result.outcome in {"REJECTED", "UNKNOWN"}:
            # A rejected/ambiguous cancel must not be interpreted as proof that the
            # original order remains untouched. Reconciliation owns the truth.
            state = "UNKNOWN"
        else:
            raise ValueError(f"unsupported cancellation outcome:{result.outcome}")
        self._request(
            "PATCH",
            "execution_orders",
            query={"environment": f"eq.{self.environment}", "order_id": f"eq.{order_id}"},
            body={"state": state, "last_internal_update_at": _utc_now()},
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
                "is_test_fixture": "eq.false",
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
