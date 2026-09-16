from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4


@dataclass
class SimOrder:
    broker_id: str
    client_order_id: str
    symbol: str
    side: str
    quantity: Decimal
    price: Decimal
    status: str
    filled_quantity: Decimal


class SimBroker:
    """Deterministic broker double; models idempotent client-order submission only."""

    def __init__(self):
        self.orders: dict[str, SimOrder] = {}
        self.by_client_order_id: dict[str, str] = {}

    def submit(self, client_order_id: str, symbol: str, side: str, quantity: Decimal, price: Decimal) -> SimOrder:
        existing_id = self.by_client_order_id.get(client_order_id)
        if existing_id is not None:
            return self.orders[existing_id]
        oid = str(uuid4())
        order = SimOrder(
            oid,
            client_order_id,
            symbol,
            side,
            quantity,
            price,
            "FILLED",
            quantity,
        )
        self.orders[oid] = order
        self.by_client_order_id[client_order_id] = oid
        return order

    def lookup_by_client_order_id(self, client_order_id: str) -> SimOrder | None:
        broker_id = self.by_client_order_id.get(client_order_id)
        return self.orders.get(broker_id) if broker_id else None

    def snapshot(self) -> list[SimOrder]:
        return list(self.orders.values())
