import pytest
import apps.trading_runtime.node as runtime_node
from apps.trading_runtime.node import SystemClock


def test_clock_accepts_small_forward_progress(monkeypatch):
    values = iter([1000.0, 1001.0])
    monkeypatch.setattr(runtime_node, "time", lambda: next(values))
    clock = SystemClock()
    assert clock.now_ms() == 1_000_000
    assert clock.now_ms() == 1_001_000


def test_clock_rejects_large_backward_jump(monkeypatch):
    values = iter([1000.0, 998.0])
    monkeypatch.setattr(runtime_node, "time", lambda: next(values))
    clock = SystemClock(max_backward_ms=100)
    clock.now_ms()
    with pytest.raises(RuntimeError, match="SYSTEM_CLOCK_MOVED_BACKWARD"):
        clock.now_ms()


def test_clock_rejects_large_forward_jump(monkeypatch):
    values = iter([1000.0, 2000.0])
    monkeypatch.setattr(runtime_node, "time", lambda: next(values))
    clock = SystemClock(max_forward_jump_ms=1000)
    clock.now_ms()
    with pytest.raises(RuntimeError, match="SYSTEM_CLOCK_JUMPED_FORWARD"):
        clock.now_ms()
