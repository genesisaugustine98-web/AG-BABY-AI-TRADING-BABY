"""Server-only Supabase persistence for broker-confirmed execution accounting.

The canonical execution path is environment-scoped, idempotent, and transactionally
applied by the database RPC. Broker fills are the only objects allowed to create
accounting state; submission acknowledgements never become fills.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

from apps.execution_gateway.mt5_fills import DealHistoryCursor
from packages.fill_accounting import BrokerConfirmedFill, FillAccountingEngine, PositionState


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _required(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty")
    return value.strip()


class SupabaseExecutionStore:
    """Server-side execution persistence and broker-deal identity resolution."""

    def __init__(
        self,
        *,
        url: str | None = None,
        key: str | None = None,
        environment: str = "demo",
        timeout_seconds: int = 10,
    ):
        self.url = (url or os.getenv("SUPABASE_URL", "")).rstrip("/")
        # SERVICE_ROLE is the canonical secret name. Keep SECRET_KEY as a temporary
        # compatibility fallback for existing worker deployments, never for clients.
        self.key = key or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SECRET_KEY", "")
        self.environment = _required(environment, "environment")
        self.timeout_seconds = timeout_seconds
        if not self.url or not self.key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
        if not self.url.startswith("https://"):
            raise RuntimeError("SUPABASE_URL must use https")
        if self.environment not in {"paper", "demo", "live"}:
            raise RuntimeError("unsupported execution environment")

    def _request(
        self,
        method: str,
        table: str,
        *,
        query: Mapping[str, str] | None = None,
        payload: Any = None,
        prefer: str | None = None,
    ) -> Any:
        params = urllib.parse.urlencode(query or {})
        endpoint = f"{self.url}/rest/v1/{table}"
        if params:
            endpoint = f"{endpoint}?{params}"
        body = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8") if payload is not None else None
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        request = urllib.request.Request(endpoint, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                content = response.read().decode("utf-8")
                return json.loads(content) if content else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Supabase {table} request failed with HTTP {exc.code}: {detail[:500]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Supabase {table} connection failed: {exc.reason}") from exc

    def _rpc(self, function: str, payload: Mapping[str, Any]) -> list[dict[str, Any]]:
        endpoint = f"{self.url}/rest/v1/rpc/{urllib.parse.quote(function, safe='')}"
        body = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=body,
            method="POST",
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                content = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Supabase RPC {function} failed with HTTP {exc.code}: {detail[:500]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Supabase RPC {function} connection failed: {exc.reason}") from exc
        if not content:
            return []
        decoded = json.loads(content)
        if isinstance(decoded, list):
            return decoded
        if isinstance(decoded, dict):
            return [decoded]
        raise RuntimeError(f"Supabase RPC {function} returned invalid data")

    def resolve(self, broker_order_id: str, instrument: str, side: str) -> str | None:
        """Resolve a broker order ticket to exactly one internal order in this environment."""
        broker_order_id = _required(broker_order_id, "broker_order_id")
        instrument = _required(instrument, "instrument")
        side = _required(side, "side").lower()
        if side not in {"buy", "sell"}:
            raise ValueError("side must be BUY or SELL")
        rows = self._request(
            "GET",
            "execution_orders",
            query={
                "select": "order_id,client_order_id,broker_order_id,instrument,side,environment,state",
                "environment": f"eq.{self.environment}",
                "broker_order_id": f"eq.{broker_order_id}",
                "instrument": f"eq.{instrument}",
                "side": f"eq.{side}",
            },
        ) or []
        if len(rows) != 1:
            # Zero = not yet bound. More than one = ambiguous identity; the caller
            # deliberately treats both cases as unresolved and does not advance the
            # broker-deal watermark past the ambiguous observation.
            return None
        order_id = str(rows[0].get("order_id") or "").strip()
        client_order_id = str(rows[0].get("client_order_id") or "").strip()
        if not order_id or not client_order_id:
            return None
        return order_id

    def load_ingestion_checkpoint(self, *, environment: str, source: str, stream: str) -> DealHistoryCursor:
        environment = _required(environment, "environment")
        source = _required(source, "source")
        stream = _required(stream, "stream")
        rows = self._request(
            "GET",
            "execution_ingestion_checkpoints",
            query={
                "environment": f"eq.{environment}",
                "source": f"eq.{source}",
                "stream": f"eq.{stream}",
                "select": "watermark_msc,overlap_msc",
            },
        ) or []
        if not rows:
            return DealHistoryCursor()
        if len(rows) != 1:
            raise RuntimeError(f"ingestion_checkpoint_identity_ambiguous:{environment}:{source}:{stream}")
        return DealHistoryCursor(
            watermark_msc=int(rows[0]["watermark_msc"]),
            overlap_msc=int(rows[0]["overlap_msc"]),
        )

    def save_ingestion_checkpoint(
        self,
        *,
        environment: str,
        source: str,
        stream: str,
        cursor: DealHistoryCursor,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        environment = _required(environment, "environment")
        source = _required(source, "source")
        stream = _required(stream, "stream")
        payload = {
            "environment": environment,
            "source": source,
            "stream": stream,
            "watermark_msc": cursor.watermark_msc,
            "overlap_msc": cursor.overlap_msc,
            "metadata": dict(metadata or {}),
            "updated_at": _utc_now(),
        }
        self._request(
            "POST",
            "execution_ingestion_checkpoints",
            query={"on_conflict": "environment,source,stream"},
            payload=payload,
            prefer="resolution=merge-duplicates,return=minimal",
        )

    def _order_for_fill(self, order_id: str) -> dict[str, Any]:
        rows = self._request(
            "GET",
            "execution_orders",
            query={
                "select": "order_id,client_order_id,broker_order_id,environment,instrument,side",
                "order_id": f"eq.{_required(order_id, 'order_id')}",
            },
        ) or []
        if len(rows) != 1:
            raise RuntimeError(f"internal_order_identity_ambiguous:{order_id}")
        return rows[0]

    def ingest(self, fill: BrokerConfirmedFill) -> PositionState:
        """Apply one confirmed fill through the atomic database accounting boundary."""
        fill.validate()
        order = self._order_for_fill(fill.order_id)
        if str(order["environment"]) != self.environment:
            raise RuntimeError("fill environment mismatch")
        if str(order["instrument"]) != fill.instrument:
            raise RuntimeError("fill instrument mismatch")
        if str(order["side"]).lower() != fill.side.lower():
            raise RuntimeError("fill side mismatch")
        client_order_id = str(order.get("client_order_id") or "").strip()
        if not client_order_id:
            raise RuntimeError("internal order has no client_order_id")

        result = self._rpc(
            "apply_broker_confirmed_fill",
            {
                "p_environment": self.environment,
                "p_fill_id": fill.fill_id,
                "p_order_id": fill.order_id,
                "p_broker_fill_id": fill.broker_fill_id,
                "p_broker_order_id": fill.broker_order_id,
                "p_client_order_id": client_order_id,
                "p_instrument": fill.instrument,
                "p_side": fill.side,
                "p_quantity": str(fill.quantity),
                "p_price": str(fill.price),
                "p_filled_at": fill.filled_at,
                "p_broker": "mt5",
                "p_commission": str(fill.commission),
                "p_financing": str(fill.financing),
                "p_metadata": dict(fill.metadata),
            },
        )
        if len(result) != 1:
            raise RuntimeError("confirmed-fill accounting returned no unique position")
        row = result[0]
        return PositionState(
            instrument=str(row["instrument"]),
            net_quantity=Decimal(str(row["net_quantity"])),
            average_price=Decimal(str(row["average_price"])),
            realized_pnl=Decimal(str(row["realized_pnl"])),
        )

    def insert_fill(self, fill: BrokerConfirmedFill) -> tuple[str, bool]:
        """Legacy compatibility path; new workers should call ingest() for atomic accounting."""
        fill.validate()
        payload = {
            "fill_id": fill.fill_id,
            "order_id": fill.order_id,
            "broker_fill_id": fill.broker_fill_id,
            "filled_at": fill.filled_at,
            "quantity": str(fill.quantity),
            "price": str(fill.price),
            "side": fill.side.lower(),
            "venue": "mt5",
            "commission": str(fill.commission),
            "financing": str(fill.financing),
            "metadata": {
                **dict(fill.metadata),
                "instrument": fill.instrument,
                "accounting_fingerprint": fill.fingerprint,
                "source_truth": "broker_confirmed_fill",
            },
            "created_at": _utc_now(),
        }
        existing = self._request(
            "GET",
            "execution_fills",
            query={"fill_id": f"eq.{fill.fill_id}", "select": "*"},
        )
        if existing:
            if len(existing) != 1:
                raise RuntimeError(f"execution_fill_identity_ambiguous:{fill.fill_id}")
            row = existing[0]
            fingerprint = ((row.get("metadata") or {}).get("accounting_fingerprint"))
            if fingerprint != fill.fingerprint:
                raise RuntimeError(f"fill_id_conflict:{fill.fill_id}")
            return fill.fill_id, False
        self._request("POST", "execution_fills", payload=payload, prefer="return=minimal")
        return fill.fill_id, True

    def load_fills(self, instrument: str, *, environment: str | None = None) -> tuple[BrokerConfirmedFill, ...]:
        """Load canonical fills only for orders belonging to the requested environment."""
        instrument = _required(instrument, "instrument")
        target_environment = _required(environment or self.environment, "environment")
        orders = self._request(
            "GET",
            "execution_orders",
            query={
                "select": "order_id",
                "environment": f"eq.{target_environment}",
                "instrument": f"eq.{instrument}",
            },
        ) or []
        order_ids = [str(row["order_id"]) for row in orders if row.get("order_id")]
        if not order_ids:
            return ()

        fills: list[BrokerConfirmedFill] = []
        # Keep PostgREST URLs bounded for instruments with many historical orders.
        for offset in range(0, len(order_ids), 250):
            batch = order_ids[offset : offset + 250]
            order_filter = "in.(" + ",".join(f'"{value.replace(chr(34), chr(34) * 2)}"' for value in batch) + ")"
            rows = self._request(
                "GET",
                "execution_fills",
                query={
                    "select": "fill_id,order_id,broker_fill_id,filled_at,quantity,price,side,venue,commission,financing,metadata",
                    "order_id": order_filter,
                    "order": "filled_at.asc,fill_id.asc",
                },
            ) or []
            for row in rows:
                metadata = dict(row.get("metadata") or {})
                source_instrument = metadata.get("instrument", instrument)
                if source_instrument != instrument:
                    continue
                fills.append(
                    BrokerConfirmedFill(
                        fill_id=str(row["fill_id"]),
                        order_id=str(row["order_id"]),
                        instrument=source_instrument,
                        side=str(row["side"]).upper(),
                        quantity=Decimal(str(row["quantity"])),
                        price=Decimal(str(row["price"])),
                        filled_at=str(row["filled_at"]),
                        broker_fill_id=row.get("broker_fill_id"),
                        broker_order_id="",
                        venue=row.get("venue"),
                        commission=Decimal(str(row["commission"])),
                        financing=Decimal(str(row["financing"])),
                        metadata=metadata,
                    )
                )
        return tuple(fills)

    def upsert_position(self, *, environment: str, state: PositionState) -> None:
        position_id = "pos-" + hashlib.sha256(f"{environment}:{state.instrument}".encode("utf-8")).hexdigest()[:24]
        payload = {
            "position_id": position_id,
            "environment": environment,
            "instrument": state.instrument,
            "net_quantity": str(state.net_quantity),
            "average_price": str(state.average_price),
            "realized_pnl": str(state.realized_pnl),
            "financing_pnl": "0",
            "state": "FLAT" if state.net_quantity == 0 else ("OPEN" if state.net_quantity > 0 else "OPEN"),
            "metadata": {"projection": "deprecated_non_atomic_projection"},
            "updated_at": _utc_now(),
        }
        self._request(
            "POST",
            "execution_positions",
            payload=payload,
            prefer="resolution=merge-duplicates,return=minimal",
        )


class DurableFillAccountingBridge:
    """Compatibility wrapper around the atomic Supabase fill-accounting path."""

    def __init__(self, store: SupabaseExecutionStore, *, environment: str):
        self.store = store
        self.environment = _required(environment, "environment")
        if self.environment != store.environment:
            raise ValueError("bridge/store environment mismatch")

    def ingest(self, fill: BrokerConfirmedFill) -> PositionState:
        if self.environment not in {"paper", "demo", "live"}:
            raise RuntimeError("unsupported execution environment")
        return self.store.ingest(fill)


__all__ = ["DurableFillAccountingBridge", "SupabaseExecutionStore"]
