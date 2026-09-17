"""Demo-only reconciliation and confirmed-deal ingestion loop.

This worker runs only in a trusted server/worker environment. Broker submissions are
not performed here; the loop ingests actual MT5 deals, binds them to durable internal
orders, atomically accounts the confirmed fills, and then reconciles current broker
truth before execution can be considered available.
"""
from __future__ import annotations

import os
import time

from apps.execution_gateway.mt5_gateway import DemoOnlyMT5Gateway
from apps.execution_gateway.mt5_fills import MT5FillIngestionService
from integrations.supabase_execution import SupabaseExecutionStore as FillStore
from integrations.supabase_execution_store import SupabaseExecutionStore as ReconciliationStore
from .service import DurableReconciliationService
from .worker import ReconciliationWorker


def main() -> None:
    if os.environ.get("EXECUTION_ENV", "demo") != "demo":
        raise RuntimeError("refusing to start: reconciliation entrypoint is demo-only")
    interval = max(5.0, float(os.environ.get("RECONCILIATION_INTERVAL_SECONDS", "15")))
    group = os.environ.get("MT5_DEAL_GROUP") or None

    gateway = DemoOnlyMT5Gateway()
    reconciliation_store = ReconciliationStore(environment="demo")
    fill_store = FillStore(environment="demo")

    gateway.connect_and_verify_demo()
    ingestion = MT5FillIngestionService(gateway.deal_collector(), fill_store, fill_store)
    worker = ReconciliationWorker(gateway, reconciliation_store, reconciliation_store)
    service = DurableReconciliationService(worker)
    startup = service.startup()
    print(f"reconciliation startup state={startup.state.value} persisted_frozen={startup.recovered_frozen}")

    try:
        while True:
            try:
                # Deal ingestion precedes snapshot reconciliation so the internal
                # order/position projection reflects broker-confirmed executions.
                fill_result, cursor = ingestion.ingest_checkpointed(
                    checkpoint_store=fill_store,
                    environment="demo",
                    source="mt5",
                    stream="deals",
                    now_msc=int(time.time() * 1000),
                    group=group,
                )
                if fill_result.unresolved:
                    reconciliation_store.set_frozen(
                        True,
                        reason=f"unresolved_mt5_deals:{len(fill_result.unresolved)}:watermark={cursor.watermark_msc}",
                    )
                    print(
                        f"deal_ingestion applied={fill_result.applied} unresolved={len(fill_result.unresolved)} "
                        f"watermark={cursor.watermark_msc} trading_permitted=False"
                    )

                result = service.reconcile_once()
                print(
                    f"reconciliation captured_at={result.captured_at} "
                    f"status={result.status} fills_applied={fill_result.applied} "
                    f"unresolved={len(fill_result.unresolved)} "
                    f"trading_permitted={service.trading_permitted}"
                )
            except Exception as exc:
                # The service/store has already attempted to persist the freeze on
                # reconciliation failures; ingestion failures are explicitly frozen here.
                reconciliation_store.set_frozen(True, reason=f"worker_exception:{type(exc).__name__}")
                print(f"reconciliation error={type(exc).__name__}")
            time.sleep(interval)
    finally:
        gateway.shutdown()


if __name__ == "__main__":
    main()
