"""Deterministic runtime fault/soak harness with explicit recovery gates."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

class FaultKind(str, Enum):
    NONE="NONE"; MARKET_DATA="MARKET_DATA"; RECONCILIATION="RECONCILIATION"; SUPABASE="SUPABASE"
    LEASE_LOST="LEASE_LOST"; BROKER_UNKNOWN="BROKER_UNKNOWN"; EMERGENCY_FREEZE="EMERGENCY_FREEZE"
    RESTART="RESTART"; RECONCILIATION_READY="RECONCILIATION_READY"

@dataclass(frozen=True)
class FaultPlan:
    cycles:int
    faults:dict[int,FaultKind]
    def __post_init__(self):
        if self.cycles<1: raise ValueError("cycles must be >= 1")
        if any(i<0 or i>=self.cycles for i in self.faults): raise ValueError("fault cycle is outside plan")

@dataclass(frozen=True)
class SoakReport:
    cycles:int; freezes:int; recoveries:int; invariant_violations:tuple[str,...]; terminal_state:str

class DeterministicSoakHarness:
    def __init__(self):
        self.state="RUNNING"; self.freezes=0; self.recoveries=0; self.violations=[]
    def run(self, plan:FaultPlan)->SoakReport:
        for step in range(plan.cycles):
            fault=plan.faults.get(step,FaultKind.NONE)
            if fault in {FaultKind.MARKET_DATA,FaultKind.RECONCILIATION,FaultKind.SUPABASE,FaultKind.LEASE_LOST,FaultKind.BROKER_UNKNOWN,FaultKind.EMERGENCY_FREEZE}:
                if self.state!="FROZEN": self.state="FROZEN"; self.freezes+=1
                continue
            if fault==FaultKind.RESTART: self.state="STARTING"; continue
            if fault==FaultKind.RECONCILIATION_READY:
                if self.state=="STARTING": self.state="RUNNING"; self.recoveries+=1
                elif self.state=="FROZEN": self.violations.append(f"ILLEGAL_FREEZE_CLEAR_AT_CYCLE:{step}")
                continue
            if self.state=="FROZEN":
                continue
            if self.state!="RUNNING": self.violations.append(f"INVALID_ACTIVE_STATE:{step}:{self.state}")
        return SoakReport(plan.cycles,self.freezes,self.recoveries,tuple(self.violations),self.state)

__all__=["DeterministicSoakHarness","FaultKind","FaultPlan","SoakReport"]
