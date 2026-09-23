from decimal import Decimal
from packages.demo_execution import SubmissionResult
from packages.execution_kernel import ExecutionKernel
from tests.test_execution_kernel import context, intent, spec


class Repo:
    def __init__(self):
        self.order=type("O",(),{"order_id":"o1","state":"INTENDED","broker_order_id":None})()
        self.observations=[]

    def ensure_intended(self,*args):
        return self.order

    def record_execution_observation(self,order_id,observation):
        self.observations.append((order_id,observation))

    def mark_submitting(self,order_id):
        return self.order

    def record_submission(self,order_id,result):
        if result.broker_order_id: self.order.broker_order_id=result.broker_order_id
        self.order.state="ACKNOWLEDGED" if result.outcome=="ACCEPTED" else result.outcome
        return self.order

class Broker:
    def __init__(self): self.requests=[]
    def submit(self,request):
        self.requests.append(request)
        return SubmissionResult("ACCEPTED",broker_order_id="b1")


def test_kernel_persists_execution_observation_and_expiry():
    repo=Repo(); broker=Broker()
    result=ExecutionKernel().execute(intent=intent(),context=context(),instrument=spec(),repository=repo,broker=broker)
    assert result.decision=="SUBMITTED"
    assert repo.observations[0][1]["decision_mid"]=="150.001"
    assert broker.requests[0].expires_at_ms==5000
