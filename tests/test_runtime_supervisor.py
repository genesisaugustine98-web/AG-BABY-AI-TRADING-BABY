from packages.runtime_supervisor import RuntimeState, RuntimeSupervisor


def test_supervisor_reaches_running_and_reports_health():
    supervisor = RuntimeSupervisor(node_id="test-node", max_heartbeat_age_ms=1_000)
    supervisor.start()
    supervisor.mark_ready(10_000)
    health = supervisor.health(10_500)
    assert supervisor.state == RuntimeState.RUNNING
    assert health.healthy
    assert health.heartbeat_age_ms == 500


def test_supervisor_freezes_and_rejects_operational_claim():
    supervisor = RuntimeSupervisor(node_id="test-node")
    supervisor.start()
    supervisor.mark_ready(10_000)
    supervisor.freeze("broker-drift")
    assert supervisor.state == RuntimeState.FROZEN
    try:
        supervisor.assert_operational(10_001)
    except RuntimeError as exc:
        assert str(exc) == "broker-drift"
    else:
        raise AssertionError("frozen runtime must not be operational")


def test_supervisor_detects_stale_heartbeat():
    supervisor = RuntimeSupervisor(node_id="test-node", max_heartbeat_age_ms=100)
    supervisor.start()
    supervisor.mark_ready(10_000)
    health = supervisor.health(10_101)
    assert not health.healthy
    assert health.reason == "HEARTBEAT_STALE"
