"""Safe broker command semantics around the existing execution identity."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .models import OrderState


class CommandType(str, Enum):
    CANCEL = "CANCEL"
    REPLACE = "REPLACE"
    EXPIRE = "EXPIRE"


@dataclass(frozen=True)
class CommandValidation:
    allowed: bool
    reasons: tuple[str, ...]


_TERMINAL = {OrderState.FILLED, OrderState.REJECTED, OrderState.CANCELED, OrderState.FREEZE}
_CANCELABLE = {OrderState.ACCEPTED, OrderState.PARTIAL}
_REPLACEABLE = {OrderState.ACCEPTED, OrderState.PARTIAL}
_EXPIREABLE = {OrderState.AUTHORIZED, OrderState.ACCEPTED, OrderState.PARTIAL}


def validate_order_command(
    *,
    command: CommandType,
    state: OrderState,
    broker_order_id: str | None,
) -> CommandValidation:
    reasons: list[str] = []
    if state in _TERMINAL:
        reasons.append("TERMINAL_ORDER_STATE")
    if not broker_order_id or not broker_order_id.strip():
        reasons.append("BROKER_ORDER_ID_REQUIRED")
    if command == CommandType.CANCEL and state not in _CANCELABLE:
        reasons.append("ORDER_NOT_CANCELABLE_IN_STATE")
    elif command == CommandType.REPLACE and state not in _REPLACEABLE:
        reasons.append("ORDER_NOT_REPLACEABLE_IN_STATE")
    elif command == CommandType.EXPIRE and state not in _EXPIREABLE:
        reasons.append("ORDER_NOT_EXPIREABLE_IN_STATE")
    if state in {OrderState.UNKNOWN, OrderState.RECONCILING}:
        reasons.append("UNKNOWN_ORDER_STATE_REQUIRES_TRUTH")
    return CommandValidation(not reasons, tuple(dict.fromkeys(reasons)))


__all__ = ["CommandType", "CommandValidation", "validate_order_command"]
