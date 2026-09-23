from datetime import datetime, timezone
from types import MethodType

import pytest

from integrations.supabase_runtime_lease import LeaseLost, SupabaseRuntimeLease


@pytest.fixture()
def lease(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "server-only")
    return SupabaseRuntimeLease(
        environment="demo",
        lease_name="ag-demo",
        owner_id="node-a",
        ttl_seconds=15,
    )


def test_lease_acquire_and_renew_is_fenced(lease):
    calls = []

    def rpc(self, function_name, body):
        calls.append((function_name, body))
        if function_name == "runtime_acquire_lease":
            return [{
                "lease_name": "ag-demo",
                "owner_id": "node-a",
                "fencing_token": 7,
                "lease_until": "2026-09-23T08:00:00+00:00",
            }]
        return [{
            "lease_name": "ag-demo",
            "owner_id": "node-a",
            "fencing_token": 7,
            "lease_until": "2026-09-23T08:00:15+00:00",
        }]

    lease._rpc = MethodType(rpc, lease)
    acquired = lease.acquire()
    renewed = lease.renew()
    assert acquired.fencing_token == 7
    assert renewed.fencing_token == 7
    assert calls[1][1]["p_fencing_token"] == 7


def test_lease_loss_fails_closed(lease):
    lease._rpc = MethodType(
        lambda self, function_name, body: [{
            "lease_name": "ag-demo",
            "owner_id": "node-a",
            "fencing_token": 2,
            "lease_until": datetime.now(timezone.utc).isoformat(),
        }]
    )
    lease.acquire()

    lease._rpc = MethodType(lambda self, function_name, body: [])
    with pytest.raises(LeaseLost):
        lease.renew()
    assert lease.record is None


def test_lease_rejects_bad_ttl(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "server-only")
    with pytest.raises(ValueError):
        SupabaseRuntimeLease(environment="demo", lease_name="x", owner_id="y", ttl_seconds=4)
