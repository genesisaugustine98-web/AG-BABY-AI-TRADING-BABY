from dataclasses import FrozenInstanceError

from packages.events import HeartbeatEvent
from integrations.runtime_event_store import RuntimeEventStore


def test_event_serialization_is_json_safe_and_stable():
    event = HeartbeatEvent("e1", 1_000, "node", "1", "node-a", "RUNNING", "HEALTHY")
    payload = RuntimeEventStore._jsonable(event)
    assert payload["event_id"] == "e1"
    assert payload["state"] == "RUNNING"
    assert RuntimeEventStore._stable_hash(event) == RuntimeEventStore._stable_hash(event)


def test_event_immutability():
    event = HeartbeatEvent("e1", 1_000, "node", "1", "node-a", "RUNNING", "HEALTHY")
    try:
        event.state = "FROZEN"
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError("runtime events must be immutable")
