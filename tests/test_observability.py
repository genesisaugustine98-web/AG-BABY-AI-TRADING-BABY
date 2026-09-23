from packages.events import FreezeEvent, OrderLifecycleEvent
from packages.observability import RuntimeAlertRouter
from packages.models import OrderState

def test_freeze_and_unknown_generate_alerts():
    received=[]
    router=RuntimeAlertRouter(lambda **kwargs: received.append(kwargs))
    freeze=FreezeEvent("e1",1000,"node","v1","demo","FAILSAFE")
    router.observe(freeze)
    unknown=OrderLifecycleEvent("e2",1001,"node","v1","c1","o1",OrderState.UNKNOWN,"b1","UNKNOWN",("timeout",))
    router.observe(unknown)
    assert [x["severity"] for x in received]==["CRITICAL","CRITICAL"]
    assert received[0]["alert_key"]=="RUNTIME_FREEZE"
    assert received[1]["alert_key"]=="EXECUTION_UNKNOWN"
