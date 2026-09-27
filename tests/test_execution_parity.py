from decimal import Decimal
from packages.execution_parity import compare_execution_contracts
from tests.test_execution_kernel import context, intent, spec

def test_demo_and_paper_contracts_match():
    result=compare_execution_contracts(demo_intent=intent(),demo_context=context(),demo_instrument=spec(),paper_intent=intent(),paper_context=context(),paper_instrument=spec())
    assert result.compatible

def test_contract_change_is_detected():
    original=intent()
    changed=type(original)(original.intent_id,original.strategy_id,original.strategy_version,original.policy_version,original.symbol,original.side,original.quantity,original.order_type,
        Decimal("151"),original.stop_price,original.target_price,original.created_at_ms,original.expires_at_ms,original.max_slippage_fraction,original.risk_fraction,original.horizon_seconds,original.evidence_ids)
    result=compare_execution_contracts(demo_intent=original,demo_context=context(),demo_instrument=spec(),paper_intent=changed,paper_context=context(),paper_instrument=spec())
    assert not result.compatible
