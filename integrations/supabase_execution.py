"""Server-only Supabase persistence for broker-confirmed execution accounting.

This adapter is intended for a worker/backend process, never a browser. It uses the
server-side Supabase secret key already used by the repository's integration worker.
A fill is inserted idempotently by fill_id; an existing row is compared field-by-field
before it can be treated as the same immutable fill. Positions are then deterministically
replayed from persisted fills and upserted by (environment, instrument).
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
    def __init__(self, *, url: str | None = None, key: str | None = None, timeout_seconds: int = 10):
        self.url = (url or os.getenv("SUPABASE_URL", "")).rstrip("/")
        self.key = key or os.getenv("SUPABASE_SECRET_KEY", "")
        self.timeout_seconds = timeout_seconds
        if not self.url or not self.key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SECRET_KEY are required")

    def _request(self, method: str, table: str, *, query: Mapping[str, str] | None = None, payload: Any = None, prefer: str | None = None) -> Any:
        params = urllib.parse.urlencode(query or {})
        endpoint = f"{self.url}/rest/v1/{table}"
        if params:
            endpoint = f"{endpoint}?{params}"
        body = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8") if payload is not None else None
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
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

    def insert_fill(self, fill: BrokerConfirmedFill) -> tuple[str, bool]:
        payload = {
            "fill_id": fill.fill_id,
            "order_id": fill.order_id,
            "broker_fill_id": fill.broker_fill_id,
            "filled_at": fill.filled_at,
            "quantity": str(fill.quantity),
            "price": str(fill.price),
            "side": fill.side,
            "venue": fill.venue,
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

    def load_fills(self, instrument: str) -> tuple[BrokerConfirmedFill, ...]:
        instrument = _required(instrument, "instrument")
        rows = self._request(
            "GET",
            "execution_fills",
            query={
                "select": "fill_id,order_id,broker_fill_id,filled_at,quantity,price,side,venue,commission,financing,metadata",
                "metadata->>instrument": f"eq.{instrument}",
                "metadata->>source_truth": "eq.broker_confirmed_fill",
                "order": "filled_at.asc,fill_id.asc",
            },
        ) or []
        fills: list[BrokerConfirmedFill] = []
        for row in rows:
            metadata = dict(row.get("metadata") or {})
            source_instrument = metadata.get("instrument")
            if source_instrument != instrument:
                continue
            fills.append(
                BrokerConfirmedFill(
                    fill_id=row["fill_id"],
                    order_id=row["order_id"],
                    instrument=source_instrument,
                    side=row["side"],
                    quantity=Decimal(str(row["quantity"])),
                    price=Decimal(str(row["price"])),
                    filled_at=row["filled_at"],
                    broker_fill_id=row.get("broker_fill_id"),
                    venue=row.get("venue"),
                    commission=Decimal(str(row["commission"])),
                    financing=Decimal(str(row["financing"])),
                    metadata=metadata,
                )
            )
        return tuple(fills)

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
        row = rows[0]
        return DealHistoryCursor(
            watermark_msc=int(row["watermark_msc"]),
            overlap_msc=int(row["overlap_msc"]),
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

    def upsert_position(self, *, environment: str, state: PositionState) -> None:
        position_id = "pos-" + hashlib.sha256(f"{environment}:{state.instrument}".encode("utf-8")).hexdigest()[:24]
        payload = {
            "position_id": position_id,
            "environment": environment,
            "instrument": state.instrument,
            "net_quantity": str(state.net_quantity),
            "average_price": str(state.average_price) if state.average_price is not None else None,
            "realized_pnl": str(state.realized_pnl),
            "financing_pnl": str(state.financing_pnl),
            "state": "FLAT" if state.net_quantity == 0 else ("LONG" if state.net_quantity > 0 else "SHORT"),
            "metadata": {
                "projection": "persisted_broker_confirmed_fills",
                "pnl_basis": "quote_currency_units_assuming_base_quantity",
                "account_currency_conversion": "UNKNOWN",
            },
            "updated_at": _utc_now(),
        }
        self._request(
            "POST",
            "execution_positions",
            payload=payload,
            prefer="resolution=merge-duplicates,return=minimal",
        )


class DurableFillAccountingBridge:
    def __init__(self, store: SupabaseExecutionStore, *, environment: str):
        if not environment.strip():
            raise ValueError("environment must be non-empty")
        self.store = store
        self.environment = environment.strip()

    def ingest(self, fill: BrokerConfirmedFill) -> PositionState:
        self.store.insert_fill(fill)
        engine = FillAccountingEngine()
        for persisted in self.store.load_fills(fill.instrument):
            engine.ingest(persisted)
        state = engine.position(fill.instrument)
        self.store.upsert_position(environment=self.environment, state=state)
        return state


__all__ = ["DurableFillAccountingBridge", "SupabaseExecutionStore"]
