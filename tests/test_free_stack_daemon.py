from apps.research.free_stack_daemon import Health


def test_health_defaults_fail_closed():
    h = Health(started_at_ms=1)
    assert h.running
    assert h.last_success_at_ms == 0
    assert h.observations == 0
    assert h.failures == 0
