"""Server-only persistence for risk, opportunities, models and research lineage."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Mapping

from packages.opportunity import OpportunityCandidate
from packages.research_quality import MultipleTestingResult


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SupabaseControlPlaneStore:
    def __init__(self, *, environment: str = "demo", timeout_seconds: float = 10.0) -> None:
        self.environment = environment.strip().lower()
        if self.environment not in {"research", "paper", "demo", "live"}:
            raise ValueError("invalid control-plane environment")
        self.url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        self.key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SECRET_KEY", "")
        self.timeout_seconds = timeout_seconds
        if not self.url or not self.key:
            raise RuntimeError("SUPABASE_URL and server-side Supabase key are required")
        if not self.url.startswith("https://"):
            raise RuntimeError("SUPABASE_URL must use https")

    def _request(self, table: str, payload: Mapping[str, Any]) -> None:
        endpoint = f"{self.url}/rest/v1/{urllib.parse.quote(table, safe='')}"
        body = json.dumps(dict(payload), separators=(",", ":"), default=str).encode("utf-8")
        request = urllib.request.Request(
            endpoint,
            data=body,
            method="POST",
            headers={
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds):
                return
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Supabase control-plane write failed:{table}:{exc.code}:{detail[:400]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Supabase control-plane connection failed:{table}:{exc.reason}") from exc

    def record_risk_decision(
        self,
        *,
        intent_id: str,
        decision: str,
        reasons: tuple[str, ...] = (),
        order_id: str | None = None,
        estimated_loss: Any = None,
        order_risk_fraction: Any = None,
        projected_gross_risk_fraction: Any = None,
        policy_version: str | None = None,
        model_id: str | None = None,
        model_version: str | None = None,
        evidence_ids: tuple[str, ...] = (),
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        self._request(
            "risk_decisions",
            {
                "environment": self.environment,
                "intent_id": intent_id,
                "order_id": order_id,
                "decision": decision,
                "reasons": list(reasons),
                "estimated_loss": estimated_loss,
                "order_risk_fraction": order_risk_fraction,
                "projected_gross_risk_fraction": projected_gross_risk_fraction,
                "policy_version": policy_version,
                "model_id": model_id,
                "model_version": model_version,
                "evidence_ids": list(evidence_ids),
                "payload": dict(payload or {}),
            },
        )

    def record_opportunity(self, candidate: OpportunityCandidate) -> None:
        self._request(
            "opportunity_candidates",
            {
                "candidate_id": candidate.candidate_id,
                "environment": self.environment,
                "instrument": candidate.instrument,
                "side": candidate.side,
                "expected_return": candidate.expected_return,
                "probability_up": candidate.probability if candidate.side == "BUY" else 1 - candidate.probability,
                "calibration_score": candidate.calibration_score,
                "estimated_cost": candidate.estimated_cost,
                "executable_edge": candidate.executable_edge,
                "suggested_risk": candidate.suggested_risk,
                "state": candidate.state,
                "model_id": candidate.model_id,
                "model_version": candidate.model_version,
                "evidence_ids": [],
                "market_state": {},
                "payload": {"reason": candidate.reason, "safety_margin": str(candidate.safety_margin)},
            },
        )

    def register_model(
        self,
        *,
        model_id: str,
        version: str,
        status: str,
        artifact_uri: str | None = None,
        dataset_fingerprint: str | None = None,
        code_commit_sha: str | None = None,
        metrics: Mapping[str, Any] | None = None,
        calibration: Mapping[str, Any] | None = None,
        feature_version: str | None = None,
    ) -> None:
        self._request(
            "model_registry",
            {
                "model_id": model_id,
                "version": version,
                "status": status,
                "artifact_uri": artifact_uri,
                "dataset_fingerprint": dataset_fingerprint,
                "code_commit_sha": code_commit_sha,
                "metrics": dict(metrics or {}),
                "calibration": dict(calibration or {}),
                "feature_version": feature_version,
            },
        )

    def register_research_run(
        self,
        *,
        run_id: str,
        hypothesis_id: str | None,
        dataset_fingerprint: str | None,
        code_commit_sha: str | None,
        config: Mapping[str, Any],
        status: str,
        artifact_uri: str | None = None,
        summary: Mapping[str, Any] | None = None,
        completed_at: str | None = None,
    ) -> None:
        self._request(
            "research_runs",
            {
                "run_id": run_id,
                "hypothesis_id": hypothesis_id,
                "dataset_fingerprint": dataset_fingerprint,
                "code_commit_sha": code_commit_sha,
                "config": dict(config),
                "status": status,
                "started_at": _now(),
                "completed_at": completed_at,
                "artifact_uri": artifact_uri,
                "summary": dict(summary or {}),
            },
        )


__all__ = ["SupabaseControlPlaneStore"]
