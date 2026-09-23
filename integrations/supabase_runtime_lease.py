"""Postgres-backed fenced runtime lease for multi-host execution deployments."""
from __future__ import annotations

import json
import os
import ssl
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class LeaseRecord:
    lease_name: str
    owner_id: str
    fencing_token: int
    lease_until: datetime


class LeaseLost(RuntimeError):
    """Raised when a runtime no longer owns its fencing token."""


class SupabaseRuntimeLease:
    def __init__(
        self,
        *,
        environment: str,
        lease_name: str,
        owner_id: str,
        ttl_seconds: int = 30,
        timeout_seconds: float = 5.0,
    ) -> None:
        self.environment = environment.strip().lower()
        self.lease_name = lease_name.strip()
        self.owner_id = owner_id.strip()
        self.ttl_seconds = int(ttl_seconds)
        self.timeout_seconds = float(timeout_seconds)
        self._record: LeaseRecord | None = None

        if self.environment not in {"research", "paper", "demo"}:
            raise ValueError("unsupported lease environment")
        if not self.lease_name or not self.owner_id:
            raise ValueError("lease_name and owner_id are required")
        if self.ttl_seconds < 5 or self.ttl_seconds > 300:
            raise ValueError("ttl_seconds must be between 5 and 300")
        base = os.environ.get("SUPABASE_URL", "").rstrip("/")
        key = os.environ.get("SUPABASE_SECRET_KEY", "") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if not base or not key:
            raise RuntimeError("SUPABASE_URL and server-side Supabase key are required")
        if not base.startswith("https://"):
            raise RuntimeError("SUPABASE_URL must use https")
        self.base_url = base
        self.api_key = key

    @property
    def record(self) -> LeaseRecord | None:
        return self._record

    def acquire(self) -> LeaseRecord:
        rows = self._rpc(
            "runtime_acquire_lease",
            {
                "p_lease_name": self.lease_name,
                "p_environment": self.environment,
                "p_owner_id": self.owner_id,
                "p_ttl_seconds": self.ttl_seconds,
            },
        )
        if not rows:
            raise LeaseLost(f"runtime lease is held by another owner:{self.lease_name}")
        self._record = self._parse(rows[0])
        return self._record

    def renew(self) -> LeaseRecord:
        current = self._record
        if current is None:
            raise LeaseLost("cannot renew a lease that has not been acquired")
        rows = self._rpc(
            "runtime_renew_lease",
            {
                "p_lease_name": self.lease_name,
                "p_owner_id": self.owner_id,
                "p_fencing_token": current.fencing_token,
                "p_ttl_seconds": self.ttl_seconds,
            },
        )
        if not rows:
            self._record = None
            raise LeaseLost(f"runtime lease lost:{self.lease_name}")
        self._record = self._parse(rows[0])
        return self._record

    def release(self) -> bool:
        current = self._record
        if current is None:
            return False
        rows = self._rpc(
            "runtime_release_lease",
            {
                "p_lease_name": self.lease_name,
                "p_owner_id": self.owner_id,
                "p_fencing_token": current.fencing_token,
            },
        )
        released = bool(rows and (rows[0] is True or rows[0].get("runtime_release_lease") is True))
        self._record = None
        return released

    def _rpc(self, function_name: str, body: dict[str, object]):
        qs = urllib.parse.urlencode({})
        del qs
        url = f"{self.base_url}/rest/v1/rpc/{function_name}"
        data = json.dumps(body, separators=(",", ":")).encode()
        headers = {
            "apikey": self.api_key,
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds, context=ssl.create_default_context()) as response:
                raw = response.read().decode("utf-8")
                value = json.loads(raw) if raw else []
                if isinstance(value, dict):
                    return [value]
                if isinstance(value, list):
                    return value
                return [value]
        except Exception as exc:
            raise LeaseLost(f"Supabase runtime lease call failed:{function_name}") from exc

    @staticmethod
    def _parse(row: dict[str, object]) -> LeaseRecord:
        lease_until = row.get("lease_until")
        if not lease_until:
            raise LeaseLost("lease response did not include lease_until")
        parsed = datetime.fromisoformat(str(lease_until).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return LeaseRecord(
            lease_name=str(row["lease_name"]),
            owner_id=str(row["owner_id"]),
            fencing_token=int(row["fencing_token"]),
            lease_until=parsed.astimezone(timezone.utc),
        )


__all__ = ["LeaseLost", "LeaseRecord", "SupabaseRuntimeLease"]
