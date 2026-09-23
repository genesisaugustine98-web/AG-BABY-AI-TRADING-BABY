from packages.event_bus import EventBus
from packages.events import FreezeEvent, HeartbeatEvent


def event(reason: str):
    return FreezeEvent("e1", 1_000, "test", "1", "demo", reason)


def test_event_bus_routes_typed_and_wildcard_handlers():
    bus = EventBus(history_limit=3)
    typed = []
    all_events = []
    bus.subscribe(FreezeEvent, typed.append)
    bus.subscribe(None, all_events.append)
    bus.publish(event("A"))
    bus.publish(event("B"))
    bus.publish(HeartbeatEvent("e2", 1_001, "test", "1", "node", "RUNNING", "HEALTHY"))
    assert [x.reason for x in typed] == ["A", "B"]
    assert len(all_events) == 3
    assert len(bus.history()) == 3


def test_noncritical_handler_failure_is_recorded():
    bus = EventBus()

    def broken(_):
        raise RuntimeError("boom")

    bus.subscribe(FreezeEvent, broken)
    bus.publish(event("A"))
    assert bus.failures()[0].error_type == "RuntimeError"


def test_critical_handler_failure_surfaces():
    bus = EventBus()

    def broken(_):
        raise RuntimeError("boom")

    bus.subscribe(FreezeEvent, broken, critical=True)
    try:
        bus.publish(event("A"))
    except RuntimeError:
        pass
    else:
        raise AssertionError("critical failure should surface")
