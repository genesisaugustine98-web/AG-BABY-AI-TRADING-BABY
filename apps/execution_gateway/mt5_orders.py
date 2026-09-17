"""Demo-only MT5 order submission and broker-truth lookup.

This adapter is intentionally conservative: it refuses non-demo environments,
validates broker symbol constraints, calls order_check before order_send, and
returns acknowledgement only. Executed quantity enters accounting only through
the separate deal-history ingestion path.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from types import SimpleNamespace
from typing import Any

from packages.demo_execution import SubmissionRequest, SubmissionResult


@dataclass(frozen=True)
class MT5OrderReceipt:
    accepted: bool
    broker_order_id: str | None
    retcode: int | None
    comment: str
    raw: dict[str, Any]


class DemoOnlyMT5OrderAdapter:
    def __init__(self, mt5_api: Any):
        if os.getenv("EXECUTION_ENV", "demo") != "demo":
            raise RuntimeError("MT5 order submission is demo-only")
        self.mt5 = mt5_api

    @staticmethod
    def _step_volume(value: Decimal, minimum: Decimal, maximum: Decimal, step: Decimal) -> Decimal:
        if minimum <= 0 or maximum < minimum or step <= 0:
            raise ValueError("invalid broker volume specification")
        if value < minimum or value > maximum:
            raise ValueError("requested volume outside broker bounds")
        steps = ((value - minimum) / step).to_integral_value(rounding=ROUND_DOWN)
        normalized = minimum + steps * step
        if normalized <= 0 or normalized > maximum:
            raise ValueError("requested volume cannot be normalized")
        return normalized

    def _symbol_info(self, symbol: str) -> Any:
        info = self.mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError(f"symbol_info unavailable:{symbol}")
        if getattr(info, "visible", True) is False:
            self.mt5.symbol_select(symbol, True)
            info = self.mt5.symbol_info(symbol)
            if info is None:
                raise RuntimeError(f"symbol_select failed:{symbol}")
        return info

    def _request(self, request: SubmissionRequest) -> tuple[dict[str, Any], Any]:
        info = self._symbol_info(request.symbol)
        minimum = Decimal(str(getattr(info, "volume_min", "0")))
        maximum = Decimal(str(getattr(info, "volume_max", "0")))
        step = Decimal(str(getattr(info, "volume_step", "0")))
        volume = self._step_volume(request.quantity, minimum, maximum, step)
        tick = self.mt5.symbol_info_tick(request.symbol)
        if tick is None:
            raise RuntimeError(f"symbol_tick unavailable:{request.symbol}")

        side = request.side.upper()
        if side == "BUY":
            order_type = getattr(self.mt5, "ORDER_TYPE_BUY")
            default_price = Decimal(str(getattr(tick, "ask")))
        elif side == "SELL":
            order_type = getattr(self.mt5, "ORDER_TYPE_SELL")
            default_price = Decimal(str(getattr(tick, "bid")))
        else:
            raise ValueError("side must be BUY or SELL")

        action = getattr(self.mt5, "TRADE_ACTION_DEAL")
        if request.order_type.upper() in {"LIMIT", "BUY_LIMIT", "SELL_LIMIT"}:
            action = getattr(self.mt5, "TRADE_ACTION_PENDING")
            if side == "BUY":
                order_type = getattr(self.mt5, "ORDER_TYPE_BUY_LIMIT")
            else:
                order_type = getattr(self.mt5, "ORDER_TYPE_SELL_LIMIT")
        price = Decimal(str(request.limit_price)) if request.limit_price is not None else default_price

        payload = {
            "action": action,
            "symbol": request.symbol,
            "volume": float(volume),
            "type": order_type,
            "price": float(price),
            "sl": float(request.limit_price if False else 0),
            "tp": float(0),
            "deviation": int(os.getenv("MT5_MAX_DEVIATION_POINTS", "20")),
            "magic": int(os.getenv("MT5_MAGIC", "260917")),
            "comment": request.client_order_id,
            "type_time": getattr(self.mt5, "ORDER_TIME_GTC", 0),
            "type_filling": getattr(info, "filling_mode", getattr(self.mt5, "ORDER_FILLING_FOK", 0)),
        }
        # Stop/target values live in the TradeIntent, while MT5's request object
        # requires exact broker-side price semantics. The execution kernel passes
        # them through a richer adapter in the next stage; this safe baseline keeps
        # the demo submission path market-only unless the order type is explicit.
        return payload, info

    def submit(self, request: SubmissionRequest) -> SubmissionResult:
        payload, _ = self._request(request)
        check = self.mt5.order_check(SimpleNamespace(**payload))
        if check is None:
            raise RuntimeError(f"order_check failed:{self.mt5.last_error()}")
        check_retcode = getattr(check, "retcode", 0)
        failed_check = getattr(self.mt5, "TRADE_RETCODE_DONE", -1)
        if check_retcode not in {0, failed_check}:
            return SubmissionResult("REJECTED", reason=f"order_check_retcode:{check_retcode}")
        result = self.mt5.order_send(SimpleNamespace(**payload))
        if result is None:
            raise RuntimeError(f"order_send failed:{self.mt5.last_error()}")
        retcode = int(getattr(result, "retcode", -1))
        accepted_codes = {
            getattr(self.mt5, "TRADE_RETCODE_DONE", -999999),
            getattr(self.mt5, "TRADE_RETCODE_PLACED", -999998),
            getattr(self.mt5, "TRADE_RETCODE_DONE_PARTIAL", -999997),
        }
        if retcode not in accepted_codes:
            return SubmissionResult("REJECTED", reason=f"order_send_retcode:{retcode}")
        order_id = getattr(result, "order", None)
        return SubmissionResult(
            "ACCEPTED",
            broker_order_id=None if order_id is None else str(order_id),
            filled_quantity=Decimal("0"),
            reason=f"retcode:{retcode}",
        )

    def lookup_by_client_order_id(self, client_order_id: str) -> SubmissionResult | None:
        client_order_id = client_order_id.strip()
        if not client_order_id:
            raise ValueError("client_order_id must be non-empty")
        active = self.mt5.orders_get()
        if active is None:
            raise RuntimeError(f"orders_get failed:{self.mt5.last_error()}")
        matches = [o for o in active if str(getattr(o, "comment", "")).strip() == client_order_id]
        if len(matches) > 1:
            raise RuntimeError(f"ambiguous_active_order:{client_order_id}")
        if matches:
            order = matches[0]
            state = str(getattr(order, "state", ""))
            return SubmissionResult("ACCEPTED", broker_order_id=str(getattr(order, "ticket")), reason=state)

        history = self.mt5.history_orders_get()
        if history is None:
            raise RuntimeError(f"history_orders_get failed:{self.mt5.last_error()}")
        matches = [o for o in history if str(getattr(o, "comment", "")).strip() == client_order_id]
        if not matches:
            return None
        if len(matches) > 1:
            matches = sorted(matches, key=lambda o: (getattr(o, "time_done_msc", 0), getattr(o, "ticket", 0)), reverse=True)
        order = matches[0]
        state = str(getattr(order, "state", ""))
        rejected = "REJECT" in state.upper() or "CANCEL" in state.upper() or "EXPIRE" in state.upper()
        return SubmissionResult(
            "REJECTED" if rejected else "ACCEPTED",
            broker_order_id=str(getattr(order, "ticket")),
            reason=state,
        )

    def cancel(self, broker_order_id: str) -> SubmissionResult:
        request = {
            "action": getattr(self.mt5, "TRADE_ACTION_REMOVE"),
            "order": int(broker_order_id),
        }
        result = self.mt5.order_send(SimpleNamespace(**request))
        if result is None:
            raise RuntimeError(f"order_cancel failed:{self.mt5.last_error()}")
        retcode = int(getattr(result, "retcode", -1))
        return SubmissionResult(
            "ACCEPTED" if retcode == getattr(self.mt5, "TRADE_RETCODE_DONE", -999999) else "REJECTED",
            broker_order_id=broker_order_id,
            reason=f"retcode:{retcode}",
        )


__all__ = ["DemoOnlyMT5OrderAdapter", "MT5OrderReceipt"]
