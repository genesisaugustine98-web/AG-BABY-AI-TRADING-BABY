"""Optional source-health publisher for the Supabase control plane.

Credentials are read only from the process environment. Failure to publish health must
never be interpreted as permission to trade; callers decide whether to freeze.
"""
from __future__ import annotations

import json
import os
from urllib.request import Request, urlopen


class SupabaseSourceHealthPublisher:
    def __init__(self, *, url: str | None = None, secret_key: str | None = None, timeout_seconds: float = 5.0) -> None:
        self.url = (url or os.getenv("SUPABASE_URL", "")).rstrip("/")
        self.secret_key = secret_key or os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.url and self.secret_key)

    def publish(self, *, source_id: str, health: float, metadata: dict[str, object] | None = None) -> None:
        if not self.configured:
            return
        if not 0.0 <= health <= 1.0:
            raise ValueError("health must be in [0,1]")
        payload = json.dumps({
            "source_id": source_id,
            "health": health,
            "metadata": metadata or {},
        }).encode("utf-8")
        request = Request(
            f"{self.url}/rest/v1/data_source_registry?on_conflict=source_id",
            data=payload,
            method="POST",
            headers={
                "apikey": self.secret_key,
                "Authorization": f"Bearer {self.secret_key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            if response.status >= 300:
                raise RuntimeError(f"supabase health write failed:{response.status}")


__all__ = ["SupabaseSourceHealthPublisher"]
