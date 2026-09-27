from decimal import Decimal

from packages.prop_rules import PropAccountState, PropRuleSet, check_entry


def state(**overrides):
    values = dict(
        equity=Decimal("10000"),
        start_of_day_equity=Decimal("10000"),
        high_watermark_equity=Decimal("10000"),
        open_positions=0,
        trading_days_completed=5,
        utc_hour=12,
        is_weekend=False,
    )
    values.update(overrides)
    return PropAccountState(**values)


def test_prop_rule_adapter_is_explicit():
    rules = PropRuleSet("demo", Decimal("0.05"), Decimal("0.10"), 5, ea_allowed=True)
    check = check_entry(
        rules=rules,
        state=state(),
        additional_risk_fraction=Decimal("0.005"),
        expected_hold_seconds=3600,
        opens_new_position=True,
    )
    assert check.allowed
    assert not check.reasons


def test_prop_rule_adapter_fails_closed_near_daily_limit():
    rules = PropRuleSet("demo", Decimal("0.05"), Decimal("0.10"), 5)
    check = check_entry(
        rules=rules,
        state=state(equity=Decimal("9550")),
        additional_risk_fraction=Decimal("0.01"),
        expected_hold_seconds=3600,
        opens_new_position=True,
    )
    assert not check.allowed
    assert "DAILY_LOSS_BUFFER_INSUFFICIENT" in check.reasons


def test_prop_rule_adapter_can_block_automation():
    rules = PropRuleSet("contest", Decimal("0.05"), Decimal("0.10"), 5, ea_allowed=False)
    check = check_entry(
        rules=rules,
        state=state(),
        additional_risk_fraction=Decimal("0.001"),
        expected_hold_seconds=300,
        opens_new_position=True,
    )
    assert not check.allowed
    assert "AUTOMATION_NOT_ALLOWED" in check.reasons
