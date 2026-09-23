"""Demo-only MT5 order submission and broker-truth lookup.

This adapter validates broker constraints, calls order_check before order_send, and
returns acknowledgement only. Executed quantity enters accounting only through the
separate MT5 deal-history ingestion path. UNKNOWN recovery searches a bounded history
window and never retries submission automatically.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
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
        steps = (value - minimum) / step
        if steps != steps.to_integral_value(rounding=ROUND_DOWN):
            raise ValueError("requested volume is not aligned to broker volume step")
        return value

    def _symbol_info(self, symbol: str) -> Any:
        info = self.mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError(f"symbol_info unavailable:{symbol}")
        if getattr(info, "visible", True) is False:
            selected = self.mt5.symbol_select(symbol, True)
            if selected is False:
                raise RuntimeError(f"symbol_select failed:{symbol}")
            info = self.mt5.symbol_info(symbol)
            if info is None:
                raise RuntimeError(f"symbol_info unavailable after select:{symbol}")
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
        bid = Decimal(str(getattr(tick, "bid", "0")))
        ask = Decimal(str(getattr(tick, "ask", "0")))
        tick_time = int(getattr(tick, "time", 0) or 0)
        if bid <= 0 or ask <= 0 or tick_time <= 0:
            raise RuntimeError(f"invalid_or_stale_symbol_tick:{request.symbol}")

        side = request.side.upper()
        if side == "BUY":
            order_type = getattr(self.mt5, "ORDER_TYPE_BUY")
            default_price = Decimal(str(getattr(tick, "ask")))
        elif side == "SELL":
            order_type = getattr(self.mt5, "ORDER_TYPE_SELL")
            default_price = Decimal(str(getattr(tick, "bid")))
        else:
            raise ValueError("side must be BUY or SELL")

        order_kind = request.order_type.upper()
        action = getattr(self.mt5, "TRADE_ACTION_DEAL")
        is_pending = order_kind in {"LIMIT", "BUY_LIMIT", "SELL_LIMIT"}
        if is_pending:
            action = getattr(self.mt5, "TRADE_ACTION_PENDING")
            order_type = getattr(self.mt5, "ORDER_TYPE_BUY_LIMIT" if side == "BUY" else "ORDER_TYPE_SELL_LIMIT")
        price = Decimal(str(request.limit_price)) if request.limit_price is not None else default_price

        stop = Decimal(str(request.stop_price)) if request.stop_price is not None else Decimal("0")
        target = Decimal(str(request.target_price)) if request.target_price is not None else Decimal("0")
        if stop and ((side == "BUY" and stop >= default_price) or (side == "SELL" and stop <= default_price)):
            raise ValueError("protective stop is on the wrong side of the market")
        if target and ((side == "BUY" and target <= default_price) or (side == "SELL" and target >= default_price)):
            raise ValueError("protective target is on the wrong side of the market")

        type_time = int(getattr(self.mt5, "ORDER_TIME_GTC", 0))
        expiration = None
        if is_pending and request.expires_at_ms:
            if request.expires_at_ms <= tick_time * 1000:
                raise ValueError("pending order expiration must be in the future")
            specified = getattr(self.mt5, "ORDER_TIME_SPECIFIED", None)
            if specified is None:
                raise RuntimeError("broker does not expose specified order expiration")
            type_time = int(specified)
            expiration = int(request.expires_at_ms // 1000)

        payload = {
            "action": action,
            "symbol": request.symbol,
            "volume": float(volume),
            "type": order_type,
            "price": float(price),
            "sl": float(stop),
            "tp": float(target),
            "deviation": int(os.getenv("MT5_MAX_DEVIATION_POINTS", "20")),
            "magic": int(os.getenv("MT5_MAGIC", "260917")),
            "comment": request.client_order_id,
            "type_time": type_time,
            **({"expiration": expiration} if expiration is not None else {}),
            "type_filling": (
                int(getattr(self.mt5, "ORDER_FILLING_RETURN"))
                if is_pending
                else self._filling_mode(info)
            ),
        }, info

    def _filling_mode(self, info: Any) -> int:
        """Choose a filling policy that the symbol/execution mode actually permits."""
        flags = int(getattr(info, "filling_mode", 0) or 0)
        fok_flag = int(getattr(self.mt5, "SYMBOL_FILLING_FOK", 1))
        ioc_flag = int(getattr(self.mt5, "SYMBOL_FILLING_IOC", 2))
        if flags & fok_flag:
            return int(getattr(self.mt5, "ORDER_FILLING_FOK"))
        if flags & ioc_flag:
            return int(getattr(self.mt5, "ORDER_FILLING_IOC"))
        execution_mode = getattr(self.mt5, "SYMBOL_TRADE_EXECUTION_MARKET", 2)
        if int(getattr(info, "trade_exemode", execution_mode)) != int(execution_mode):
            return int(getattr(self.mt5, "ORDER_FILLING_RETURN"))
        raise RuntimeError("no_compatible_market_filling_policy")

    def submit(self, request: SubmissionRequest) -> SubmissionResult:
        payload, _ = self._request(request)
        check = self.mt5.order_check(payload)
        if check is None:
            raise RuntimeError(f"order_check failed:{self.mt5.last_error()}")
        check_retcode = int(getattr(check, "retcode", 0))
        done_code = getattr(self.mt5, "TRADE_RETCODE_DONE", -1)
        if check_retcode not in {0, done_code}:
            return SubmissionResult("REJECTED", reason=f"order_check_retcode:{check_retcode}")
        result = self.mt5.order_send(payload)
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
        return SubmissionResult("ACCEPTED", broker_order_id=None if order_id is None else str(order_id), filled_quantity=Decimal("0"), reason=f"retcode:{retcode}")

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
            return SubmissionResult("ACCEPTED", broker_order_id=str(getattr(order, "ticket")), reason=str(getattr(order, "state", "")))

        lookback_hours = max(1, int(os.getenv("MT5_RECOVERY_LOOKBACK_HOURS", "72")))
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=lookback_hours)
        history = self.mt5.history_orders_get(start, now)
        if history is None:
            raise RuntimeError(f"history_orders_get failed:{self.mt5.last_error()}")
        matches = [o for o in history if str(getattr(o, "comment", "")).strip() == client_order_id]
        if not matches:
            return None
        matches = sorted(matches, key=lambda o: (getattr(o, "time_done_msc", 0), getattr(o, "ticket", 0)), reverse=True)
        order = matches[0]
        state = str(getattr(order, "state", ""))
        upper = state.upper()
        if any(token in upper for token in ("REJECT", "CANCEL", "EXPIRE")):
            outcome = "REJECTED"
        else:
            outcome = "ACCEPTED"
        return SubmissionResult(outcome, broker_order_id=str(getattr(order, "ticket")), reason=state)

    def cancel(self, broker_order_id: str) -> SubmissionResult:
        request = {"action": getattr(self.mt5, "TRADE_ACTION_REMOVE"), "order": int(broker_order_id)}
        result = self.mt5.order_send(request)
        if result is None:
            raise RuntimeError(f"order_cancel failed:{self.mt5.last_error()}")
        retcode = int(getattr(result, "retcode", -1))
        return SubmissionResult("ACCEPTED" if retcode == getattr(self.mt5, "TRADE_RETCODE_DONE", -999999) else "REJECTED", broker_order_id=broker_order_id, reason=f"retcode:{retcode}")

    def _active_order(self, broker_order_id: str) -> Any | None:
        orders_get = getattr(self.mt5, "orders_get", None)
        if not callable(orders_get):
            raise RuntimeError("broker does not expose active-order lookup")
        orders = orders_get()
        if orders is None:
            raise RuntimeError(f"orders_get failed:{self.mt5.last_error()}")
        ticket = int(broker_order_id)
        matches = [order for order in orders if int(getattr(order, "ticket", 0) or 0) == ticket]
        if len(matches) > 1:
            raise RuntimeError(f"ambiguous_active_order_ticket:{broker_order_id}")
        return matches[0] if matches else None

    def replace(
        self,
        broker_order_id: str,
        *,
        symbol: str,
        side: str,
        limit_price: Decimal,
        stop_price: Decimal | None,
        target_price: Decimal | None,
        expires_at_ms: int = 0,
    ) -> SubmissionResult:
        current = self._active_order(broker_order_id)
        if current is None:
            return SubmissionResult("UNKNOWN", broker_order_id=str(broker_order_id), reason="ACTIVE_ORDER_NOT_FOUND")
        allowed_types = {
            int(getattr(self.mt5, name, -1))
            for name in ("ORDER_TYPE_BUY_LIMIT", "ORDER_TYPE_SELL_LIMIT", "ORDER_TYPE_BUY_STOP", "ORDER_TYPE_SELL_STOP")
        }
        if int(getattr(current, "type", -1)) not in allowed_types:
            return SubmissionResult("REJECTED", broker_order_id=str(broker_order_id), reason="MARKET_ORDER_REPLACE_UNSUPPORTED")
        if limit_price <= 0:
            raise ValueError("replacement limit price must be positive")
        if expires_at_ms and expires_at_ms <= 0:
            raise ValueError("replacement expiration must be positive when supplied")
        request: dict[str, Any] = {
            "action": int(getattr(self.mt5, "TRADE_ACTION_MODIFY")),
            "order": int(broker_order_id),
            "price": float(limit_price),
            "sl": float(stop_price or Decimal("0")),
            "tp": float(target_price or Decimal("0")),
            "type_time": int(getattr(self.mt5, "ORDER_TIME_GTC", 0)),
        }
        if expires_at_ms:
            request["type_time"] = int(getattr(self.mt5, "ORDER_TIME_SPECIFIED"))
            request["expiration"] = int(expires_at_ms // 1000)
        check = self.mt5.order_check(request)
        if check is None:
            raise RuntimeError(f"order_modify_check failed:{self.mt5.last_error()}")
        check_retcode = int(getattr(check, "retcode", 0))
        done_code = getattr(self.mt5, "TRADE_RETCODE_DONE", -1)
        if check_retcode not in {0, done_code}:
            return SubmissionResult("REJECTED", broker_order_id=str(broker_order_id), reason=f"order_modify_check_retcode:{check_retcode}")
        result = self.mt5.order_send(request)
        if result is None:
            raise RuntimeError(f"order_modify failed:{self.mt5.last_error()}")
        retcode = int(getattr(result, "retcode", -1))
        if retcode != done_code:
            return SubmissionResult("REJECTED", broker_order_id=str(broker_order_id), reason=f"order_modify_retcode:{retcode}")
        return SubmissionResult("ACCEPTED", broker_order_id=str(broker_order_id), reason=f"retcode:{retcode}")

    def expire(self, broker_order_id: str) -> SubmissionResult:
        result = self.cancel(broker_order_id)
        if result.outcome == "ACCEPTED":
            return SubmissionResult("ACCEPTED", broker_order_id=str(broker_order_id), reason="EXPIRED")
        if result.outcome == "UNKNOWN":
            return result
        return SubmissionResult("REJECTED", broker_order_id=str(broker_order_id), reason=result.reason or "EXPIRE_REJECTED")


__all__ = ["DemoOnlyMT5OrderAdapter", "MT5OrderReceipt"]
