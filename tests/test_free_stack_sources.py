from packages.horizon import Timeframe
from apps.research.free_stack_sources import BinancePublicClient, FREDClient, PublicHttpClient, redact_url_credentials


def test_free_stack_clients_have_expected_public_endpoints():
    assert BinancePublicClient.BASE_URL.startswith("https://")
    assert FREDClient.BASE_URL.endswith("/fred")


def test_redact_url_credentials():
    assert redact_url_credentials("https://example.test/x?api_key=secret") == "https://example.test/x"


def test_public_http_client_rejects_bad_timeout():
    try:
        PublicHttpClient(timeout_seconds=0)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_timeframe_available_for_source_smoke():
    assert Timeframe.M15.value == "M15"
