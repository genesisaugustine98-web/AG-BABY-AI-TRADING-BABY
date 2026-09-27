"""Deterministic runtime supervision state machine."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RuntimeState(str, Enum):
    CREATED = "CREATED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    FROZEN = "FROZEN"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class RuntimeHealth:
    state: RuntimeState
    last_heartbeat_ms: int | None
    heartbeat_age_ms: int | None
    healthy: bool
    reason: str | None = None


class RuntimeSupervisor:
    def __init__(self, *, node_id: str, max_heartbeat_age_ms: int = 30_000) -> None:
        node_id = node_id.strip()
        if not node_id:
            raise ValueError("node_id is required")
        if max_heartbeat_age_ms < 1:
            raise ValueError("max_heartbeat_age_ms must be >= 1")
        self.node_id = node_id
        self.max_heartbeat_age_ms = max_heartbeat_age_ms
        self._state = RuntimeState.CREATED
        self._last_heartbeat_ms: int | None = None
        self._reason: str | None = None

    @property
    def state(self) -> RuntimeState:
        return self._state

    @property
    def reason(self) -> str | None:
        return self._reason

    def start(self) -> None:
        if self._state not in {RuntimeState.CREATED, RuntimeState.STOPPED}:
            raise RuntimeError(f"cannot start from {self._state.value}")
        self._state = RuntimeState.STARTING
        self._reason = None

    def mark_ready(self, now_ms: int) -> None:
        self._require_time(now_ms)
        if self._state != RuntimeState.STARTING:
            raise RuntimeError(f"cannot mark ready from {self._state.value}")
        self._state = RuntimeState.RUNNING
        self._last_heartbeat_ms = now_ms
        self._reason = None

    def heartbeat(self, now_ms: int) -> None:
        self._require_time(now_ms)
        if self._state in {RuntimeState.STOPPING, RuntimeState.STOPPED, RuntimeState.FAILED}:
            return
        if self._state == RuntimeState.CREATED:
            raise RuntimeError("runtime must be started before heartbeat")
        self._last_heartbeat_ms = now_ms
        if self._state == RuntimeState.STARTING:
            self._state = RuntimeState.RUNNING

    def freeze(self, reason: str) -> None:
        reason = reason.strip()
        if not reason:
            raise ValueError("freeze reason is required")
        if self._state not in {RuntimeState.STOPPED, RuntimeState.FAILED}:
            self._state = RuntimeState.FROZEN
            self._reason = reason

    def fail(self, reason: str) -> None:
        reason = reason.strip()
        if not reason:
            raise ValueError("failure reason is required")
        self._state = RuntimeState.FAILED
        self._reason = reason

    def request_stop(self, now_ms: int) -> None:
        self._require_time(now_ms)
        if self._state not in {RuntimeState.STOPPED, RuntimeState.FAILED}:
            self._state = RuntimeState.STOPPING

    def complete_stop(self) -> None:
        if self._state == RuntimeState.STOPPING:
            self._state = RuntimeState.STOPPED

    def health(self, now_ms: int) -> RuntimeHealth:
        self._require_time(now_ms)
        age = None if self._last_heartbeat_ms is None else max(0, now_ms - self._last_heartbeat_ms)
        healthy = (
            self._state == RuntimeState.RUNNING
            and age is not None
            and age <= self.max_heartbeat_age_ms
            and self._reason is None
        )
        reason = self._reason
        if self._state == RuntimeState.RUNNING and age is not None and age > self.max_heartbeat_age_ms:
            healthy = False
            reason = "HEARTBEAT_STALE"
        return RuntimeHealth(self._state, self._last_heartbeat_ms, age, healthy, reason)

    def assert_operational(self, now_ms: int) -> None:
        health = self.health(now_ms)
        if not health.healthy:
            raise RuntimeError(health.reason or f"runtime_not_operational:{health.state.value}")

    @staticmethod
    def _require_time(now_ms: int) -> None:
        if now_ms <= 0:
            raise ValueError("now_ms must be positive")


__all__ = ["RuntimeHealth", "RuntimeState", "RuntimeSupervisor"]
