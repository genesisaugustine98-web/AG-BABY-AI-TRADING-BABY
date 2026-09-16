"""Restart-safe recovery policy for execution control.

A restart never clears a persisted safety freeze. Recovery requires fresh broker truth
and a clean reconciliation result before the execution gate may reopen.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class RecoveryState(str, Enum):
    BOOT = "BOOT"
    FROZEN = "FROZEN"
    RECONCILING = "RECONCILING"
    READY = "READY"


@dataclass
class RecoveryController:
    state: RecoveryState = RecoveryState.BOOT

    def hydrate(self, persisted_frozen: bool) -> RecoveryState:
        self.state = RecoveryState.FROZEN if persisted_frozen else RecoveryState.RECONCILING
        return self.state

    def broker_snapshot_received(self) -> RecoveryState:
        if self.state not in {RecoveryState.FROZEN, RecoveryState.RECONCILING}:
            raise RuntimeError(f"invalid recovery transition from {self.state}")
        self.state = RecoveryState.RECONCILING
        return self.state

    def reconciliation_result(self, matched: bool) -> RecoveryState:
        if self.state != RecoveryState.RECONCILING:
            raise RuntimeError(f"reconciliation result received in {self.state}")
        self.state = RecoveryState.READY if matched else RecoveryState.FROZEN
        return self.state

    @property
    def trading_permitted(self) -> bool:
        return self.state == RecoveryState.READY
