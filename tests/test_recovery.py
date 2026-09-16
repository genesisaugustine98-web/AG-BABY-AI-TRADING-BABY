from packages.recovery import RecoveryController, RecoveryState


def test_persisted_freeze_survives_restart():
    recovery = RecoveryController()
    assert recovery.hydrate(True) == RecoveryState.FROZEN
    assert recovery.trading_permitted is False
    recovery.broker_snapshot_received()
    assert recovery.reconciliation_result(True) == RecoveryState.READY
    assert recovery.trading_permitted is True


def test_clean_boot_starts_reconciling_not_ready():
    recovery = RecoveryController()
    assert recovery.hydrate(False) == RecoveryState.RECONCILING
    assert recovery.trading_permitted is False


def test_failed_reconciliation_re_freezes():
    recovery = RecoveryController()
    recovery.hydrate(False)
    recovery.broker_snapshot_received()
    assert recovery.reconciliation_result(False) == RecoveryState.FROZEN
    assert recovery.trading_permitted is False


def test_cannot_reopen_without_fresh_reconciliation():
    recovery = RecoveryController()
    recovery.hydrate(True)
    recovery.broker_snapshot_received()
    recovery.reconciliation_result(True)
    try:
        recovery.reconciliation_result(True)
    except RuntimeError:
        pass
    else:
        raise AssertionError("recovery reopened without a fresh reconciliation cycle")
