from packages.runtime_metrics import RuntimeMetrics


def test_metrics_track_cycle_and_execution_outcomes():
    metrics = RuntimeMetrics()
    metrics.start_cycle()
    metrics.record_strategy_decision(admitted=True)
    metrics.record_strategy_decision(admitted=False)
    metrics.record_execution(outcome="UNKNOWN")
    metrics.record_execution(outcome="REJECTED")
    metrics.finish_cycle()
    metrics.record_freeze()
    metrics.record_handler_failures(2)
    snap = metrics.snapshot()
    assert snap.cycles == 1
    assert snap.admitted_candidates == 1
    assert snap.rejected_candidates == 1
    assert snap.execution_unknown == 1
    assert snap.execution_rejected == 1
    assert snap.freezes == 1
    assert snap.handler_failures == 2
    assert snap.last_cycle_duration_ms is not None
