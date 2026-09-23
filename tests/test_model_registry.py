import os
from types import MethodType

from integrations.supabase_model_registry import SupabaseModelRegistry
from packages.tsmom_forecast import TSMOMValidation


def test_model_registry_payload_preserves_lineage(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "server-only")
    registry = SupabaseModelRegistry()
    captured = {}

    def request(self, method, table, body=None, prefer=None):
        captured["body"] = body
        return None

    registry._request = MethodType(request, registry)
    validation = TSMOMValidation(
        "m", "1", 24, 6, 100, 40, 40, 0.10, 0.90, "feature",
        "dataset", "commit", "PASS", "PASS"
    )
    registry.record_validation(model_id="m", version="1", validation=validation, status="validated", governance_state="DEMO")
    assert captured["body"]["dataset_fingerprint"] == "dataset"
    assert captured["body"]["code_commit_sha"] == "commit"
    assert captured["body"]["calibration"]["governance_state"] == "DEMO"
