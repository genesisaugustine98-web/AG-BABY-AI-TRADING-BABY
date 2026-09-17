"""Demo-only MT5 deal collection and explicit internal-order binding.

MT5 distinguishes an executed deal from an order request. This adapter reads historical
DEAL_TYPE_BUY/SELL records only and preserves broker-side deal metadata. It does not
infer a fill from an order acknowledgement. Because a broker deal ticket is not, by
itself, proof of the internal order/intent that caused it, binding to an internal
order_id is an explicit second step.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping, Protocol

from packages.fill_accounting import BrokerConfirmedFill


class MT5DealsAPI(Protocol):
    DEAL_TYPE_BUY: int
    DEAL_TYPE_SELL: int

    def history_deals_get(self, date_from: Any, date_to: Any, **kwargs: Any) -> Any: ...
    def last_error(self) -> Any: ...


_ENTRY_NAMES = {
    0: "IN",
    1: "OUT",
    2: "INOUT",
    3: "OUT_BY",
}


@dataclass(frozen=True)
class BrokerDealRecord:
    """Raw normalized broker execution record; not yet bound to an internal order."""

    broker_fill_id: str
    broker_order_id: str
    instrument: str
    side: str
    quantity: Decimal
    price: Decimal
    filled_at: str
    commission: Decimal
    financing: Decimal
    metadata: Mapping[str, Any]

    def bind_internal_order(self, internal_order_id: str) -> BrokerConfirmedFill:
        internal_order_id = internal_order_id.strip()
        if not internal_order_id:
            raise ValueError("internal_order_id must be non-empty")
        return BrokerConfirmedFill(
            fill_id=f"mt5:{self.broker_fill_id}",
            order_id=internal_order_id,
            instrument=self.instrument,
            side=self.side,
            quantity=self.quantity,
            price=self.price,
            filled_at=self.filled_at,
            broker_fill_id=self.broker_fill_id,
            broker_order_id=self.broker_order_id,
            venue="mt5",
            commission=self.commission,
            financing=self.financing,
            metadata={
                **dict(self.metadata),
                "source_truth": "broker_confirmed_fill",
                "order_id_resolution": "explicit_internal_order_binding",
            },
        )


def _execution_time(deal: Any) -> str:
    time_msc = getattr(deal, "time_msc", None)
    if time_msc is not None:
        try:
            milliseconds = int(time_msc)
            return datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError, OSError):
            pass
    raw_seconds = getattr(deal, "time", None)
    try:
        return datetime.fromtimestamp(int(raw_seconds), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError) as exc:
        raise ValueError("deal execution time is invalid") from exc


def _decimal(value: Any, field_name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"invalid {field_name}") from exc
    if not result.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return result


class MT5DealCollector:
    """Read actual MT5 deals in bounded history windows; demo-only by design."""

    def __init__(self, mt5_api: MT5DealsAPI):
        self.mt5 = mt5_api
        import os

        if os.getenv("EXECUTION_ENV", "demo") != "demo":
            raise RuntimeError("MT5 deal collection is demo-only")

    def collect(self, date_from: Any, date_to: Any, *, group: str | None = None) -> tuple[BrokerDealRecord, ...]:
        if date_from is None or date_to is None:
            raise ValueError("date_from and date_to are required")
        kwargs = {"group": group} if group else {}
        deals = self.mt5.history_deals_get(date_from, date_to, **kwargs)
        if deals is None:
            raise RuntimeError(f"history_deals_get failed: {self.mt5.last_error()}")

        normalized: list[BrokerDealRecord] = []
        for deal in deals:
            deal_type = getattr(deal, "type", None)
            if deal_type == self.mt5.DEAL_TYPE_BUY:
                side = "BUY"
            elif deal_type == self.mt5.DEAL_TYPE_SELL:
                side = "SELL"
            else:
                # Balance/credit/commission/corporate-action and other non-trade
                # history records are deliberately excluded from execution fills.
                continue

            ticket = int(getattr(deal, "ticket", 0))
            order = int(getattr(deal, "order", 0))
            symbol = str(getattr(deal, "symbol", "") or "").strip()
            quantity = _decimal(getattr(deal, "volume", 0), "volume")
            price = _decimal(getattr(deal, "price", 0), "price")
            if ticket <= 0:
                raise ValueError("trade deal is missing a valid deal ticket")
            if order <= 0:
                raise ValueError(f"trade deal {ticket} is missing a valid order ticket")
            if not symbol:
                raise ValueError(f"trade deal {ticket} is missing a symbol")
            if quantity <= 0:
                raise ValueError(f"trade deal {ticket} has non-positive volume")
            if price <= 0:
                raise ValueError(f"trade deal {ticket} has non-positive price")

            entry = getattr(deal, "entry", None)
            normalized.append(
                BrokerDealRecord(
                    broker_fill_id=str(ticket),
                    broker_order_id=str(order),
                    instrument=symbol,
                    side=side,
                    quantity=quantity,
                    price=price,
                    filled_at=_execution_time(deal),
                    commission=_decimal(getattr(deal, "commission", 0), "commission"),
                    financing=_decimal(getattr(deal, "swap", 0), "swap"),
                    metadata={
                        "source_truth": "broker_confirmed_deal",
                        "broker": "mt5",
                        "entry": _ENTRY_NAMES.get(entry, str(entry)),
                        "entry_raw": entry,
                        "position_id": str(getattr(deal, "position_id", 0)),
                        "reason": getattr(deal, "reason", None),
                        "magic": getattr(deal, "magic", None),
                        "comment": getattr(deal, "comment", "") or "",
                        "external_id": getattr(deal, "external_id", "") or "",
                        "fee": str(getattr(deal, "fee", 0)),
                        "profit": str(getattr(deal, "profit", 0)),
                        "deal_time_msc": getattr(deal, "time_msc", None),
                    },
                )
            )

        normalized.sort(key=lambda deal: (deal.filled_at, deal.broker_fill_id))
        return tuple(normalized)


def load_mt5() -> MT5DealsAPI:
    """Import the optional MetaTrader5 module only at execution-worker runtime."""
    import MetaTrader5 as mt5

    return mt5


__all__ = ["BrokerDealRecord", "MT5DealCollector", "MT5DealsAPI", "load_mt5"]
