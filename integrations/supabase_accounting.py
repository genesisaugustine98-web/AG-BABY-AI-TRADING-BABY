"""Trusted-server bridge from broker-confirmed fills to atomic Supabase accounting.

The database function owns the transaction: insert the immutable fill, reduce the
position, update durable order fill state, and append the broker-confirmed event
together. This module never accepts submission acknowledgements or unresolved
UNKNOWN outcomes as fills.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from packages.accounting import BrokerConfirmedFill


@dataclass(frozen=True)
class DurablePositionResult:
    duplicate: bool
    position_id: str
    instrument: str
    net_quantity: Decimal
    average_price: Decimal
    realized_pnl: Decimal
    financing_pnl: Decimal
    state: str


class SupabaseAccountingBridge:
    """Call the privileged, transactionally safe fill-accounting RPC from a worker."""

    def __init__(self, *, timeout_seconds: float = 10.0) -> None:
        self.base_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        self.api_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        self.timeout_seconds = timeout_seconds
        if not self.base_url or not self.api_key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required server-side")
        if not self.base_url.startswith("https://"):
            raise RuntimeError("SUPABASE_URL must use https")

    def _rpc(self, function: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        url = f"{self.base_url}/rest/v1/rpc/{urllib.parse.quote(function, safe='')}"
        body = json.dumps(payload, separators=(",", ":"), default=str).encode()
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "apikey": self.api_key,
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except Exception as exc:
            raise RuntimeError("Supabase accounting RPC failed") from exc
        if not raw:
            return []
        decoded = json.loads(raw)
        if isinstance(decoded, list):
            return decoded
        if isinstance(decoded, dict):
            return [decoded]
        raise RuntimeError("Supabase accounting RPC returned an invalid response")

    def apply(self, *, environment: str, order_id: str, fill: BrokerConfirmedFill) -> DurablePositionResult:
        fill.validate()
        if not order_id:
            raise ValueError("internal order_id is required")
        result = self._rpc(
            "apply_broker_confirmed_fill",
            {
                "p_environment": environment,
                "p_fill_id": fill.fill_id,
                "p_order_id": order_id,
                "p_broker_fill_id": fill.fill_id,
                "p_broker_order_id": fill.broker_order_id,
                "p_client_order_id": fill.client_order_id,
                "p_instrument": fill.instrument,
                "p_side": fill.side,
                "p_quantity": str(fill.quantity),
                "p_price": str(fill.price),
                "p_filled_at": fill.occurred_at.isoformat(),
                "p_broker": fill.broker,
                "p_commission": "0",
                "p_financing": "0",
                "p_metadata": {"source": "broker_confirmed_fill"},
            },
        )
        if len(result) != 1:
            raise RuntimeError("Supabase accounting RPC returned no unique position result")
        row = result[0]
        return DurablePositionResult(
            duplicate=bool(row["duplicate"]),
            position_id=str(row["position_id"]),
            instrument=str(row["instrument"]),
            net_quantity=Decimal(str(row["net_quantity"])),
            average_price=Decimal(str(row["average_price"])),
            realized_pnl=Decimal(str(row["realized_pnl"])),
            financing_pnl=Decimal(str(row["financing_pnl"])),
            state=str(row["state"]),
        )
