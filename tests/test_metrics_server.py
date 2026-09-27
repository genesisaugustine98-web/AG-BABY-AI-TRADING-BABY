from apps.trading_runtime.metrics_server import MetricsHTTPServer
import pytest


def test_metrics_server_restricts_non_loopback():
    with pytest.raises(ValueError):
        MetricsHTTPServer(host="0.0.0.0", port=9300, snapshot_provider=lambda: {})


def test_prometheus_export_is_stable():
    server = MetricsHTTPServer(port=9301, snapshot_provider=lambda: {"healthy": True, "cycles": 4})
    try:
        from apps.trading_runtime.metrics_server import _prometheus
        value = _prometheus({"healthy": True, "cycles": 4})
        assert "ag_runtime_cycles 4" in value
        assert "ag_runtime_healthy 1" in value
    finally:
        server.close()
