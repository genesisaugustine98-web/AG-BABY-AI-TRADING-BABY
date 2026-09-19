"""Demo-only MT5 deal collection and explicit internal-order binding.

MT5 distinguishes an executed deal from an order request. This adapter reads historical
DEAL_TYPE_BUY/SELL records only and preserves broker-side deal metadata. It does not
infer a fill from an order acknowledgement. Because a broker deal ticket is not, by
itself, proof of the internal order/intent that caused it, binding to an internal
order_id is an explicit second step.

Accounting convention: commission is stored as a positive fee cost; financing/swap
remains signed because it can be a credit or a debit.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping, Protocol

from packages.fill_accounting import BrokerConfirmedFill, PositionState
from apps.execution_gateway.mt5_time import broker_server_epoch_ms_to_utc_ms, utc_iso_from_broker_epoch_ms


class MT5DealsAPI(Protocol):
    DEAL_TYPE_BUY: int
    DEAL_TYPE_SELL: int

    def history_deals_get(self, date_from: Any, date_to: Any, **kwargs: Any) -> Any: ...
    def last_error(self) -> Any: ...


class InternalOrderResolver(Protocol):
    def resolve(self, broker_order_id: str, instrument: str, side: str) -> str | None: ...


class CanonicalFillSink(Protocol):
    def ingest(self, fill: BrokerConfirmedFill) -> PositionState: ...


class IngestionCheckpointStore(Protocol):
    def load_ingestion_checkpoint(self, *, environment: str, source: str, stream: str) -> "DealHistoryCursor": ...

    def save_ingestion_checkpoint(
        self,
        *,
        environment: str,
        source: str,
        stream: str,
        cursor: "DealHistoryCursor",
        metadata: Mapping[str, Any] | None = None,
    ) -> None: ...


_ENTRY_NAMES = {0: "IN", 1: "OUT", 2: "INOUT", 3: "OUT_BY"}


@dataclass(frozen=True)
class DealHistoryCursor:
    """Monotonic restart cursor with a replay overlap around the last watermark."""
    watermark_msc: int = 0
    overlap_msc: int = 5000

    def __post_init__(self) -> None:
        if self.watermark_msc < 0:
            raise ValueError("watermark_msc must be >= 0")
        if self.overlap_msc < 0:
            raise ValueError("overlap_msc must be >= 0")

    def window(self, now_msc: int) -> tuple[datetime, datetime]:
        now_msc = int(now_msc)
        if now_msc < self.watermark_msc:
            raise ValueError("now_msc must be >= watermark_msc")
        start_msc = max(0, self.watermark_msc - self.overlap_msc)
        return (
            datetime.fromtimestamp(start_msc / 1000, tz=timezone.utc),
            datetime.fromtimestamp(now_msc / 1000, tz=timezone.utc),
        )

    def advance(self, completed_through_msc: int) -> "DealHistoryCursor":
        completed_through_msc = int(completed_through_msc)
        if completed_through_msc < self.watermark_msc:
            raise ValueError("checkpoint cannot move backwards")
        return DealHistoryCursor(completed_through_msc, self.overlap_msc)


@dataclass(frozen=True)
class BrokerDealRecord:
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
            return utc_iso_from_broker_epoch_ms(milliseconds)
        except (TypeError, ValueError, OverflowError, OSError, RuntimeError):
            pass
    raw_seconds = getattr(deal, "time", None)
    try:
        return utc_iso_from_broker_epoch_ms(int(raw_seconds) * 1000)
    except (TypeError, ValueError, OverflowError, OSError, RuntimeError) as exc:
        raise ValueError("deal execution time is invalid") from exc


def _deal_time_msc(deal: BrokerDealRecord) -> int:
    normalized = deal.metadata.get("deal_time_msc")
    if normalized is not None:
        try:
            return max(0, int(normalized))
        except (TypeError, ValueError):
            pass
    timestamp = datetime.fromisoformat(deal.filled_at.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return int(timestamp.timestamp() * 1000)


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

            raw_commission = _decimal(getattr(deal, "commission", 0), "commission")
            financing = _decimal(getattr(deal, "swap", 0), "swap")
            entry = getattr(deal, "entry", None)
            raw_time_msc = getattr(deal, "time_msc", None)
            normalized_time_msc = None
            if raw_time_msc is not None:
                try:
                    normalized_time_msc = broker_server_epoch_ms_to_utc_ms(int(raw_time_msc))
                except (TypeError, ValueError, OverflowError, RuntimeError):
                    normalized_time_msc = None
            if normalized_time_msc is None:
                try:
                    raw_time = int(getattr(deal, "time"))
                    normalized_time_msc = broker_server_epoch_ms_to_utc_ms(raw_time * 1000)
                except (TypeError, ValueError, OverflowError, RuntimeError) as exc:
                    raise ValueError(f"deal {ticket} has invalid execution timestamp") from exc

            normalized.append(
                BrokerDealRecord(
                    broker_fill_id=str(ticket),
                    broker_order_id=str(order),
                    instrument=symbol,
                    side=side,
                    quantity=quantity,
                    price=price,
                    filled_at=_execution_time(deal),
                    commission=abs(raw_commission),
                    financing=financing,
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
                        "raw_commission": str(raw_commission),
                        # Internal time is normalized UTC; retain broker raw time separately for audit.
                        "deal_time_msc": normalized_time_msc,
                        "broker_time_msc": raw_time_msc,
                    },
                )
            )

        normalized.sort(key=lambda deal: (deal.filled_at, deal.broker_fill_id))
        return tuple(normalized)


@dataclass(frozen=True)
class FillBindingResult:
    applied: int
    unresolved: tuple[BrokerDealRecord, ...]


class MT5FillIngestionService:
    def __init__(self, collector: MT5DealCollector, resolver: InternalOrderResolver, sink: CanonicalFillSink):
        self.collector = collector
        self.resolver = resolver
        self.sink = sink

    def ingest_window(self, date_from: Any, date_to: Any, *, group: str | None = None) -> FillBindingResult:
        deals = self.collector.collect(date_from, date_to, group=group)
        bound: list[BrokerConfirmedFill] = []
        unresolved: list[BrokerDealRecord] = []
        for deal in deals:
            internal_order_id = self.resolver.resolve(deal.broker_order_id, deal.instrument, deal.side)
            if internal_order_id is None:
                unresolved.append(deal)
                continue
            bound.append(deal.bind_internal_order(internal_order_id))
        for fill in bound:
            self.sink.ingest(fill)
        return FillBindingResult(applied=len(bound), unresolved=tuple(unresolved))

    def ingest_checkpointed(
        self,
        *,
        checkpoint_store: IngestionCheckpointStore,
        environment: str,
        source: str,
        stream: str,
        now_msc: int,
        group: str | None = None,
    ) -> tuple[FillBindingResult, DealHistoryCursor]:
        cursor = checkpoint_store.load_ingestion_checkpoint(environment=environment, source=source, stream=stream)
        date_from, date_to = cursor.window(now_msc)
        result = self.ingest_window(date_from, date_to, group=group)
        completed_through = int(now_msc)
        if result.unresolved:
            earliest_unresolved = min(_deal_time_msc(deal) for deal in result.unresolved)
            completed_through = max(cursor.watermark_msc, earliest_unresolved)
        next_cursor = cursor.advance(completed_through)
        checkpoint_store.save_ingestion_checkpoint(
            environment=environment,
            source=source,
            stream=stream,
            cursor=next_cursor,
            metadata={"window_end_msc": int(now_msc), "applied": result.applied, "unresolved": len(result.unresolved)},
        )
        return result, next_cursor


def load_mt5() -> MT5DealsAPI:
    import MetaTrader5 as mt5
    return mt5


__all__ = [
    "BrokerDealRecord", "CanonicalFillSink", "DealHistoryCursor", "FillBindingResult", "IngestionCheckpointStore",
    "InternalOrderResolver", "MT5DealCollector", "MT5FillIngestionService", "MT5DealsAPI", "load_mt5",
]
