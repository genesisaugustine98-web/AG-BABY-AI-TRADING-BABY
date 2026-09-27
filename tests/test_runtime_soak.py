from packages.runtime_soak import DeterministicSoakHarness,FaultKind,FaultPlan

def test_soak_cannot_clear_freeze_without_restart_and_reconciliation():
    blocked=DeterministicSoakHarness().run(FaultPlan(12,{3:FaultKind.BROKER_UNKNOWN,7:FaultKind.RECONCILIATION_READY}))
    assert blocked.freezes==1 and blocked.recoveries==0
    assert "ILLEGAL_FREEZE_CLEAR_AT_CYCLE:7" in blocked.invariant_violations
    assert blocked.terminal_state=="FROZEN"

    recovered=DeterministicSoakHarness().run(FaultPlan(8,{2:FaultKind.BROKER_UNKNOWN,4:FaultKind.RESTART,5:FaultKind.RECONCILIATION_READY}))
    assert recovered.freezes==1 and recovered.recoveries==1 and recovered.invariant_violations==()
    assert recovered.terminal_state=="RUNNING"
