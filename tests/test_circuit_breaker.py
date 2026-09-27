from packages.circuit_breaker import CircuitBreakerLimits, CircuitBreakerTrip, ExecutionCircuitBreaker
import pytest


class Event:
    def __init__(self, outcome):
        self.outcome = outcome


def test_unknown_outcome_trips_immediately():
    reasons = []
    breaker = ExecutionCircuitBreaker(
        CircuitBreakerLimits(max_unknown_outcomes=1, max_rejected_outcomes=5),
        trip_callback=reasons.append,
    )
    with pytest.raises(CircuitBreakerTrip):
        breaker.observe(Event("UNKNOWN"))
    assert breaker.tripped
    assert reasons == ["EXECUTION_UNKNOWN_CIRCUIT_BREAKER"]


def test_rejections_trip_after_threshold():
    reasons = []
    breaker = ExecutionCircuitBreaker(
        CircuitBreakerLimits(max_unknown_outcomes=2, max_rejected_outcomes=2),
        trip_callback=reasons.append,
    )
    breaker.observe(Event("REJECTED"))
    with pytest.raises(CircuitBreakerTrip):
        breaker.observe(Event("REJECTED"))
    assert reasons == ["EXECUTION_REJECTION_CIRCUIT_BREAKER"]
