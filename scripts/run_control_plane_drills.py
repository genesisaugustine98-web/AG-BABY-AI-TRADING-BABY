"""Deterministic control-plane evidence drills; results are explicitly SIMULATED."""
from packages.events import FreezeEvent, OrderLifecycleEvent
from packages.fx_valuation import USDConversionGraph
from packages.observability import RuntimeAlertRouter
from packages.runtime_soak import DeterministicSoakHarness,FaultKind,FaultPlan
from packages.execution_parity import compare_execution_contracts
from tests.test_execution_kernel import context,intent,spec
from decimal import Decimal

def run_simulated_drills()->dict[str,dict]:
    out={}
    blocked=DeterministicSoakHarness().run(FaultPlan(12,{3:FaultKind.BROKER_UNKNOWN,7:FaultKind.RECONCILIATION_READY}))
    out["freeze_requires_restart"]={"status":"PASS" if blocked.terminal_state=="FROZEN" and blocked.recoveries==0 else "FAIL","details":{"report":blocked.__dict__}}
    recovered=DeterministicSoakHarness().run(FaultPlan(8,{2:FaultKind.BROKER_UNKNOWN,4:FaultKind.RESTART,5:FaultKind.RECONCILIATION_READY}))
    out["restart_requires_reconciliation"]={"status":"PASS" if recovered.terminal_state=="RUNNING" and recovered.recoveries==1 else "FAIL","details":{"report":recovered.__dict__}}
    alerts=[]
    router=RuntimeAlertRouter(lambda **kwargs: alerts.append(kwargs))
    router.observe(FreezeEvent("e1",1,"drill","1","demo","FAILSAFE"))
    router.observe(OrderLifecycleEvent("e2",2,"drill","1","c1","o1",None,"b1","UNKNOWN",("timeout",)))
    out["critical_alert_routing"]={"status":"PASS" if [x["severity"] for x in alerts]==["CRITICAL","CRITICAL"] else "FAIL","details":{"alerts":alerts}}
    parity=compare_execution_contracts(demo_intent=intent(),demo_context=context(),demo_instrument=spec(),paper_intent=intent(),paper_context=context(),paper_instrument=spec())
    out["demo_paper_parity"]={"status":"PASS" if parity.compatible else "FAIL","details":{"demo":parity.demo_fingerprint,"paper":parity.paper_fingerprint}}
    fx=USDConversionGraph({"EURGBP":Decimal("0.85"),"GBPUSD":Decimal("1.25")})
    out["cross_currency_valuation"]={"status":"PASS" if fx.rate_to_usd("EUR")==Decimal("1.0625") else "FAIL","details":{"eur_usd":str(fx.rate_to_usd("EUR"))}}
    return out
