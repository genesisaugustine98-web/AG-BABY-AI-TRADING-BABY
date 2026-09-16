"""Production-shaped demo reconciliation loop.

Run only in a trusted server/worker environment. It never places orders.
The process remains non-tradable until a fresh clean broker reconciliation completes.
"""
from __future__ import annotations

import os
import time

from apps.execution_gateway.mt5_gateway import DemoOnlyMT5Gateway
from integrations.supabase_execution_store import SupabaseExecutionStore
from .service import DurableReconciliationService
from .worker import ReconciliationWorker


def main() -> None:
    if os.environ.get("EXECUTION_ENV", "demo") != "demo":
        raise RuntimeError("refusing to start: reconciliation entrypoint is demo-only")
    interval = max(5.0, float(os.environ.get("RECONCILIATION_INTERVAL_SECONDS", "15")))

    gateway = DemoOnlyMT5Gateway()
    store = SupabaseExecutionStore(environment="demo")
    gateway.connect_and_verify_demo()
    worker = ReconciliationWorker(gateway, store, store)
    service = DurableReconciliationService(worker)
    startup = service.startup()
    print(f"reconciliation startup state={startup.state.value} persisted_frozen={startup.recovered_frozen}")

    try:
        while True:
            try:
                result = service.reconcile_once()
                print(
                    f"reconciliation captured_at={result.captured_at} "
                    f"status={result.status} trading_permitted={service.trading_permitted}"
                )
            except Exception as exc:
                # The service has already attempted to persist the freeze.
                print(f"reconciliation error={type(exc).__name__}")
            time.sleep(interval)
    finally:
        gateway.shutdown()


if __name__ == "__main__":
    main()
