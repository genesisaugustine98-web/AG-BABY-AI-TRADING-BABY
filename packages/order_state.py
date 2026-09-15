from dataclasses import dataclass
from .models import OrderState

ALLOWED = {
 OrderState.CREATED: {OrderState.VALIDATED},
 OrderState.VALIDATED: {OrderState.AUTHORIZED, OrderState.REJECTED},
 OrderState.AUTHORIZED: {OrderState.SUBMITTING, OrderState.REJECTED},
 OrderState.SUBMITTING: {OrderState.ACCEPTED, OrderState.REJECTED, OrderState.UNKNOWN},
 OrderState.ACCEPTED: {OrderState.PARTIAL, OrderState.FILLED, OrderState.CANCELED, OrderState.UNKNOWN},
 OrderState.PARTIAL: {OrderState.PARTIAL, OrderState.FILLED, OrderState.CANCELED, OrderState.UNKNOWN},
 OrderState.UNKNOWN: {OrderState.RECONCILING, OrderState.FREEZE},
 OrderState.RECONCILING: {OrderState.ACCEPTED, OrderState.PARTIAL, OrderState.FILLED, OrderState.REJECTED, OrderState.FREEZE},
 OrderState.FILLED: set(), OrderState.REJECTED: set(), OrderState.CANCELED: set(), OrderState.FREEZE: set(),
}

@dataclass
class OrderStateMachine:
    state: OrderState = OrderState.CREATED
    def transition(self, new_state: OrderState):
        if new_state not in ALLOWED[self.state]:
            raise ValueError(f'illegal transition {self.state}->{new_state}')
        self.state = new_state
        return self.state
    def can_retry(self) -> bool:
        return False
