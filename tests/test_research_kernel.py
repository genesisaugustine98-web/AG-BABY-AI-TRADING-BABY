from decimal import Decimal

import pytest

from packages.research_kernel import Observation, ReplayBar, cost_aware_replay, point_in_time, validate_observation


def obs(event: int, usable: int, bid: str = "1.1000", ask: str = "1.1002") -> Observation:
    return Observation(
        symbol="EURUSD",
        event_time_ms=event,
        usable_at_ms=usable,
        mid=(Decimal(bid) + Decimal(ask)) / Decimal("2"),
        bid=Decimal(bid),
        ask=Decimal(ask),
        source="test-feed",
        source_version="v1",
    )


def test_observation_quality_rejects_future_information():
    result = validate_observation(obs(100, 90))
    assert not result.accepted
    assert "availability_before_event" in result.reasons


def test_point_in_time_never_uses_unavailable_data():
    items = [obs(100, 120), obs(110, 110), obs(90, 150)]
    result = point_in_time(items, 120)
    assert [(x.event_time_ms, x.usable_at_ms) for x in result] == [(100, 120), (110, 110)]


def test_replay_charges_entry_and_terminal_exit_costs():
    bars = [
        ReplayBar(1, Decimal("1.0000"), 0),
        ReplayBar(2, Decimal("1.0100"), 1),
        ReplayBar(3, Decimal("1.0200"), 0),
    ]
    result = cost_aware_replay(
        bars,
        spread_fraction=Decimal("0.0010"),
        slippage_fraction=Decimal("0.0005"),
        commission_fraction=Decimal("0.0002"),
    )
    assert result.observations == 3
    assert result.trades == 2
    assert result.turnover == Decimal("2")
    assert result.total_cost == Decimal("0.0024")
    assert result.total_cost > Decimal("0")
    assert result.total_return < result.gross_return


def test_replay_rejects_non_monotonic_time():
    bars = [
        ReplayBar(2, Decimal("1.0"), 0),
        ReplayBar(1, Decimal("1.1"), 0),
    ]
    with pytest.raises(ValueError, match="strictly increasing"):
        cost_aware_replay(
            bars,
            spread_fraction=Decimal("0"),
            slippage_fraction=Decimal("0"),
            commission_fraction=Decimal("0"),
        )
