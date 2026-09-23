from dataclasses import dataclass
from decimal import Decimal
from apps.execution_gateway.order_controls import DemoOrderControls, ReplaceRequest
from packages.demo_execution import SubmissionResult

@dataclass
class Order:
    state:str
    broker_order_id:str|None
    instrument:str="EURUSD"
    side:str="BUY"

class Repo:
    def __init__(self): self.order=Order("ACKNOWLEDGED","42"); self.replace_requested=False; self.record=None; self.expire_requested=False
    def get(self,_): return self.order
    def mark_replace_requested(self,*args): self.replace_requested=True
    def record_replacement(self,_,result): self.record=result
    def mark_expire_requested(self,_): self.expire_requested=True
    def record_expiration(self,_,result): self.record=result

class Broker:
    def replace(self,broker_order_id,**kwargs): return SubmissionResult("ACCEPTED",broker_order_id=broker_order_id)
    def expire(self,broker_order_id): return SubmissionResult("ACCEPTED",broker_order_id=broker_order_id,reason="EXPIRED")

def test_replace_is_durable_then_broker_confirmed():
    repo=Repo(); result=DemoOrderControls(repo,Broker()).replace("o1",ReplaceRequest("EURUSD","BUY",Decimal("1.1")))
    assert result.allowed and repo.replace_requested and repo.record.outcome=="ACCEPTED"

def test_expire_uses_control_boundary():
    repo=Repo(); result=DemoOrderControls(repo,Broker()).expire("o1")
    assert result.allowed and repo.expire_requested and repo.record.reason=="EXPIRED"
