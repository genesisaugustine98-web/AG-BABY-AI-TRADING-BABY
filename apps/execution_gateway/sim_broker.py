from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

@dataclass
class SimOrder:
    broker_id: str; symbol: str; side: str; quantity: Decimal; price: Decimal; status: str

class SimBroker:
    """Deterministic broker double for unit/integration tests; never represents real market behavior."""
    def __init__(self): self.orders={}
    def submit(self, symbol, side, quantity, price):
        oid=str(uuid4()); self.orders[oid]=SimOrder(oid,symbol,side,quantity,price,'FILLED'); return self.orders[oid]
    def snapshot(self): return list(self.orders.values())
