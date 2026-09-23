"""Bounded MT5 broker-order event stream facade.

The MetaTrader5 Python API is polling-based, not a server-push WebSocket. This adapter provides
a restart-aware, monotonic event-stream interface over active and recent historical orders,
with durable ingestion checkpoints when supplied. It never submits, replaces or cancels orders.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from typing import Any, Protocol

from apps.execution_gateway.mt5_time import broker_server_epoch_ms_to_utc_ms
from apps.execution_gateway.mt5_fills import DealHistoryCursor


class BrokerOrderQueryAPI(Protocol):
    def orders_get(self) -> Any: ...
    def history_orders_get(self, date_from: Any, date_to: Any) -> Any: ...
    def last_error(self) -> Any: ...


class CheckpointStore(Protocol):
    def load_ingestion_checkpoint(self, *, environment: str, source: str, stream: str) -> DealHistoryCursor: ...
    def save_ingestion_checkpoint(self, *, environment: str, source: str, stream: str, cursor: DealHistoryCursor, metadata: dict[str, Any] | None = None) -> None: ...


@dataclass(frozen=True)
class BrokerOrderEvent:
    event_id: str
    broker_order_id: str
    client_order_id: str
    instrument: str
    side: str
    state: str
    event_time_ms: int
    source: str
    raw_fingerprint: str


def _event_time_ms(order: Any) -> int:
    for field in ("time_update_msc", "time_done_msc", "time_setup_msc", "time_msc"):
        raw = getattr(order, field, None)
        if raw:
            normalized = broker_server_epoch_ms_to_utc_ms(int(raw) if field.endswith("_msc") else int(raw) * 1000)
            if normalized > 0:
                return normalized
    raw = getattr(order, "time_done", None) or getattr(order, "time_setup", None) or getattr(order, "time", None)
    if raw:
        return broker_server_epoch_ms_to_utc_ms(int(raw) * 1000)
    return 0


class MT5BrokerOrderEventStream:
    def _side(self, raw_type: Any) -> str:
        try:
            value = int(raw_type)
        except (TypeError, ValueError):
            value = -1
        if value in {int(getattr(self.mt5, "ORDER_TYPE_BUY", -100)), int(getattr(self.mt5, "ORDER_TYPE_BUY_LIMIT", -101)),
                     int(getattr(self.mt5, "ORDER_TYPE_BUY_STOP", -102)), int(getattr(self.mt5, "ORDER_TYPE_BUY_STOP_LIMIT", -103))}:
            return "BUY"
        if value in {int(getattr(self.mt5, "ORDER_TYPE_SELL", -200)), int(getattr(self.mt5, "ORDER_TYPE_SELL_LIMIT", -201)),
                     int(getattr(self.mt5, "ORDER_TYPE_SELL_STOP", -202)), int(getattr(self.mt5, "ORDER_TYPE_SELL_STOP_LIMIT", -203))}:
            return "SELL"
        return "UNKNOWN"

    def _state(self, raw_state: Any) -> str:
        mapping = {
            getattr(self.mt5, "TRADE_ORDER_STATE_STARTED", object()): "SUBMITTING",
            getattr(self.mt5, "TRADE_ORDER_STATE_PLACED", object()): "ACCEPTED",
            getattr(self.mt5, "TRADE_ORDER_STATE_CANCELED", object()): "CANCELED",
            getattr(self.mt5, "TRADE_ORDER_STATE_PARTIAL", object()): "PARTIAL",
            getattr(self.mt5, "TRADE_ORDER_STATE_FILLED", object()): "FILLED",
            getattr(self.mt5, "TRADE_ORDER_STATE_REJECTED", object()): "REJECTED",
            getattr(self.mt5, "TRADE_ORDER_STATE_EXPIRED", object()): "CANCELED",
        }
        return mapping.get(raw_state, str(raw_state))
    def __init__(
        self,
        mt5_api: BrokerOrderQueryAPI,
        *,
        environment: str = "demo",
        checkpoint_store: CheckpointStore | None = None,
        source: str = "mt5",
        stream: str = "orders",
        overlap_msc: int = 5000,
    ) -> None:
        self.mt5 = mt5_api
        self.environment = environment.strip()
        if self.environment != "demo":
            raise RuntimeError("MT5 broker event stream is demo-only")
        self.checkpoint_store = checkpoint_store
        self.source = source
        self.stream = stream
        self.cursor = (
            checkpoint_store.load_ingestion_checkpoint(environment=self.environment, source=source, stream=stream)
            if checkpoint_store is not None
            else DealHistoryCursor(overlap_msc=overlap_msc)
        )
        self._seen: set[str] = set()

    def poll(self, *, now_msc: int) -> tuple[BrokerOrderEvent, ...]:
        now_msc = int(now_msc)
        date_from, date_to = self.cursor.window(now_msc)
        active = self.mt5.orders_get()
        if active is None:
            raise RuntimeError(f"orders_get failed:{self.mt5.last_error()}")
        history = self.mt5.history_orders_get(date_from, date_to)
        if history is None:
            raise RuntimeError(f"history_orders_get failed:{self.mt5.last_error()}")
        events: list[BrokerOrderEvent] = []
        max_time = self.cursor.watermark_msc
        for order in [*active, *history]:
            broker_id = str(getattr(order, "ticket", "") or "").strip()
            if not broker_id:
                continue
            event_time = _event_time_ms(order)
            if event_time <= 0 or event_time > now_msc:
                continue
            client_order_id = str(getattr(order, "comment", "") or "").strip()
            raw_state = str(getattr(order, "state", "") or "")
            instrument = str(getattr(order, "symbol", "") or "").strip()
            raw_type = getattr(order, "type", None)
            side = self._side(raw_type)
            state = self._state(getattr(order, "state", raw_state))
            payload = "|".join([
                broker_id, client_order_id, instrument, side, state, str(event_time),
                str(getattr(order, "volume_current", "")), str(getattr(order, "price_open", "")),
                str(getattr(order, "sl", "")), str(getattr(order, "tp", "")),
            ])
            fingerprint = hashlib.sha256(payload.encode()).hexdigest()
            if fingerprint in self._seen:
                continue
            self._seen.add(fingerprint)
            event_id = "mt5-order:" + hashlib.sha256(f"{broker_id}:{fingerprint}".encode()).hexdigest()[:32]
            events.append(BrokerOrderEvent(event_id, broker_id, client_order_id, instrument, side, state, event_time, "mt5", fingerprint))
            max_time = max(max_time, event_time)
        events.sort(key=lambda item: (item.event_time_ms, item.broker_order_id, item.event_id))
        self.cursor = self.cursor.advance(max_time)
        if self.checkpoint_store is not None:
            self.checkpoint_store.save_ingestion_checkpoint(
                environment=self.environment,
                source=self.source,
                stream=self.stream,
                cursor=self.cursor,
                metadata={"events": len(events), "window_end_msc": now_msc},
            )
        return tuple(events)


__all__=["BrokerOrderEvent","MT5BrokerOrderEventStream","CheckpointStore","BrokerOrderQueryAPI"]
