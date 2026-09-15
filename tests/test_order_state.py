import pytest
from packages.order_state import OrderStateMachine
from packages.models import OrderState

def test_unknown_cannot_retry():
    sm=OrderStateMachine(); sm.transition(OrderState.VALIDATED); sm.transition(OrderState.AUTHORIZED); sm.transition(OrderState.SUBMITTING); sm.transition(OrderState.UNKNOWN)
    assert not sm.can_retry()
    with pytest.raises(ValueError): sm.transition(OrderState.REJECTED)

def test_reconcile_path():
    sm=OrderStateMachine(); sm.transition(OrderState.VALIDATED); sm.transition(OrderState.AUTHORIZED); sm.transition(OrderState.SUBMITTING); sm.transition(OrderState.UNKNOWN); sm.transition(OrderState.RECONCILING); sm.transition(OrderState.FILLED)
    assert sm.state == OrderState.FILLED
