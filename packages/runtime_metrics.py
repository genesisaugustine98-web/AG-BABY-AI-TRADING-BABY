"""Dependency-free runtime metrics for health and operational review."""
from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic


@dataclass(frozen=True)
class MetricsSnapshot:
    cycles: int
    cycle_failures: int
    strategy_decisions: int
    admitted_candidates: int
    rejected_candidates: int
    execution_attempts: int
    execution_unknown: int
    execution_rejected: int
    freezes: int
    handler_failures: int
    last_cycle_duration_ms: float | None
    max_cycle_duration_ms: float | None


@dataclass
class RuntimeMetrics:
    cycles: int = 0
    cycle_failures: int = 0
    strategy_decisions: int = 0
    admitted_candidates: int = 0
    rejected_candidates: int = 0
    execution_attempts: int = 0
    execution_unknown: int = 0
    execution_rejected: int = 0
    freezes: int = 0
    handler_failures: int = 0
    last_cycle_duration_ms: float | None = None
    max_cycle_duration_ms: float | None = None
    _started_at: float | None = field(default=None, repr=False)

    def start_cycle(self) -> None:
        self.cycles += 1
        self._started_at = monotonic()

    def finish_cycle(self) -> None:
        if self._started_at is None:
            return
        duration = (monotonic() - self._started_at) * 1000
        self.last_cycle_duration_ms = duration
        self.max_cycle_duration_ms = duration if self.max_cycle_duration_ms is None else max(self.max_cycle_duration_ms, duration)
        self._started_at = None

    def record_strategy_decision(self, *, admitted: bool) -> None:
        self.strategy_decisions += 1
        if admitted:
            self.admitted_candidates += 1
        else:
            self.rejected_candidates += 1

    def record_execution(self, *, outcome: str | None) -> None:
        self.execution_attempts += 1
        normalized = str(outcome or "").upper()
        if normalized == "UNKNOWN":
            self.execution_unknown += 1
        elif normalized == "REJECTED":
            self.execution_rejected += 1

    def record_freeze(self) -> None:
        self.freezes += 1

    def record_cycle_failure(self) -> None:
        self.cycle_failures += 1

    def record_handler_failures(self, count: int) -> None:
        if count > 0:
            self.handler_failures += count

    def snapshot(self) -> MetricsSnapshot:
        return MetricsSnapshot(
            self.cycles,
            self.cycle_failures,
            self.strategy_decisions,
            self.admitted_candidates,
            self.rejected_candidates,
            self.execution_attempts,
            self.execution_unknown,
            self.execution_rejected,
            self.freezes,
            self.handler_failures,
            self.last_cycle_duration_ms,
            self.max_cycle_duration_ms,
        )


__all__ = ["MetricsSnapshot", "RuntimeMetrics"]
