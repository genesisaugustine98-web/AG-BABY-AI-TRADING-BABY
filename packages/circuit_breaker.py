"""Deterministic execution circuit breaker.

An UNKNOWN broker outcome is operationally more dangerous than an ordinary rejection because
the broker may have accepted the order while the client did not receive the acknowledgement.
The default policy therefore trips on the first UNKNOWN outcome. Repeated ordinary rejections
can also trip the runtime, preventing an unhealthy broker/session from generating a stream of
failed submissions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


class CircuitBreakerTrip(RuntimeError):
    pass


@dataclass(frozen=True)
class CircuitBreakerLimits:
    max_unknown_outcomes: int = 1
    max_rejected_outcomes: int = 5

    def __post_init__(self) -> None:
        if self.max_unknown_outcomes < 1 or self.max_rejected_outcomes < 1:
            raise ValueError("circuit breaker thresholds must be >= 1")


class ExecutionCircuitBreaker:
    def __init__(self, limits: CircuitBreakerLimits | None = None, *, trip_callback: Callable[[str], None]) -> None:
        self.limits = limits or CircuitBreakerLimits()
        self.trip_callback = trip_callback
        self.unknown_outcomes = 0
        self.rejected_outcomes = 0
        self.tripped_reason: str | None = None

    @property
    def tripped(self) -> bool:
        return self.tripped_reason is not None

    def observe(self, event) -> None:
        outcome = str(getattr(event, "outcome", "") or "").upper()
        if outcome == "UNKNOWN":
            self.unknown_outcomes += 1
            if self.unknown_outcomes >= self.limits.max_unknown_outcomes:
                self._trip("EXECUTION_UNKNOWN_CIRCUIT_BREAKER")
        elif outcome == "REJECTED":
            self.rejected_outcomes += 1
            if self.rejected_outcomes >= self.limits.max_rejected_outcomes:
                self._trip("EXECUTION_REJECTION_CIRCUIT_BREAKER")

    def _trip(self, reason: str) -> None:
        if self.tripped:
            raise CircuitBreakerTrip(self.tripped_reason or reason)
        self.tripped_reason = reason
        self.trip_callback(reason)
        raise CircuitBreakerTrip(reason)


__all__ = ["CircuitBreakerLimits", "CircuitBreakerTrip", "ExecutionCircuitBreaker"]
