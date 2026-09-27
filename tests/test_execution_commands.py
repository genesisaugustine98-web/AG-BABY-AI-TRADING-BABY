from packages.execution_commands import CommandType, validate_order_command
from packages.models import OrderState


def test_cancel_requires_broker_truth_and_nonterminal_state():
    ok = validate_order_command(
        command=CommandType.CANCEL,
        state=OrderState.ACCEPTED,
        broker_order_id="123",
    )
    assert ok.allowed


def test_unknown_order_cannot_be_cancelled_blindly():
    result = validate_order_command(
        command=CommandType.CANCEL,
        state=OrderState.UNKNOWN,
        broker_order_id="123",
    )
    assert not result.allowed
    assert "UNKNOWN_ORDER_STATE_REQUIRES_TRUTH" in result.reasons
