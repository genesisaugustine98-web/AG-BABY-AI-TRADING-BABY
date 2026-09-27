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


def test_full_envelope_chain_detects_metadata_tampering():
    event = HeartbeatEvent("e2", 2_000, "node", "2", "node-a", "RUNNING", "HEALTHY")
    event_id = RuntimeEventStore._db_event_id(event.event_id)
    payload = RuntimeEventStore._jsonable(event)
    h = RuntimeEventStore._stable_record_hash(
        event_id=event_id,
        occurred_at="1970-01-01T00:00:02+00:00",
        environment="demo",
        event_type="HeartbeatEvent",
        correlation_id=event.event_id,
        intent_id=None,
        order_id=None,
        broker_order_id=None,
        position_id=None,
        payload=payload,
        source=event.source,
        source_version=event.source_version,
        previous_event_hash=None,
    )
    row = {
        "event_id": event_id,
        "occurred_at": "1970-01-01T00:00:02+00:00",
        "environment": "demo",
        "event_type": "HeartbeatEvent",
        "correlation_id": event.event_id,
        "intent_id": None,
        "order_id": None,
        "broker_order_id": None,
        "position_id": None,
        "payload": payload,
        "source": event.source,
        "source_version": event.source_version,
        "previous_event_hash": None,
        "event_hash": h,
    }
    assert RuntimeEventStore.verify_chain((row,))[0]
    tampered = {**row, "source_version": "tampered"}
    assert not RuntimeEventStore.verify_chain((tampered,))[0]
