import pytest

from integrations.supabase_ledger import build_event


def test_build_event_defaults_to_research():
    event = build_event(
        integration_name="github",
        run_id="run-1",
        correlation_id="corr-1",
        status="success",
    )
    assert event.schema_version == "1.0"
    assert event.environment == "research"
    assert event.status == "success"


def test_live_events_are_rejected():
    with pytest.raises(ValueError, match="live"):
        build_event(
            integration_name="mt5_demo",
            run_id="run-2",
            correlation_id="corr-2",
            status="success",
            environment="live",
        )


def test_invalid_status_is_rejected():
    with pytest.raises(ValueError, match="invalid integration status"):
        build_event(
            integration_name="github",
            run_id="run-3",
            correlation_id="corr-3",
            status="unknown",
        )
