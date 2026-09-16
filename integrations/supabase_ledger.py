from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class IntegrationEvent:
    schema_version: str
    repo: str
    commit_sha: str
    integration_name: str
    run_id: str
    correlation_id: str
    environment: str
    status: str
    started_at: str
    completed_at: str
    artifact_uri: str | None = None
    failure_class: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_event(
    *,
    integration_name: str,
    run_id: str,
    correlation_id: str,
    status: str,
    started_at: str | None = None,
    completed_at: str | None = None,
    artifact_uri: str | None = None,
    failure_class: str | None = None,
    repo: str | None = None,
    commit_sha: str | None = None,
    environment: str | None = None,
) -> IntegrationEvent:
    env = environment or os.getenv("EXECUTION_ENV", "research")
    if env == "live":
        raise ValueError("live integration events are not permitted")
    if status not in {"queued", "running", "success", "failed", "blocked"}:
        raise ValueError(f"invalid integration status: {status}")
    return IntegrationEvent(
        schema_version="1.0",
        repo=repo or os.getenv("GITHUB_REPOSITORY", "unknown"),
        commit_sha=commit_sha or os.getenv("GITHUB_SHA", "unknown"),
        integration_name=integration_name,
        run_id=run_id,
        correlation_id=correlation_id,
        environment=env,
        status=status,
        started_at=started_at or _utc_now(),
        completed_at=completed_at or _utc_now(),
        artifact_uri=artifact_uri,
        failure_class=failure_class,
    )


def publish_event(event: IntegrationEvent, *, timeout_seconds: int = 10) -> dict[str, Any]:
    """Publish with a server-side Supabase Secret key. Never use this in a browser."""
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SECRET_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SECRET_KEY are required")
    if event.environment == "live":
        raise RuntimeError("live integration publishing is disabled")

    payload = json.dumps(asdict(event)).encode("utf-8")
    request = urllib.request.Request(
        f"{url}/rest/v1/integration_events",
        data=payload,
        method="POST",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
            return {
                "status_code": response.status,
                "body": json.loads(body) if body else None,
            }
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase publish failed with HTTP {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Supabase publish connection failed: {exc.reason}") from exc
