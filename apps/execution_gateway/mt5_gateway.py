"""Optional MT5 adapter. Secrets are read from environment; demo proof is fail-closed."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from apps.execution_gateway.mt5_fills import BrokerDealRecord, MT5DealCollector
from packages.broker_truth import BrokerPositionTruth, BrokerSnapshot
from packages.execution_ledger import BrokerOrderTruth


class DemoOnlyMT5Gateway:
    def __init__(self):
        self.server = os.environ.get("MT5_SERVER", "")
        self.allowed_server = os.environ.get("MT5_DEMO_SERVER", "")
        self.login = os.environ.get("MT5_LOGIN", "")
        self.password = os.environ.get("MT5_PASSWORD", "")
        self.terminal = os.environ.get("MT5_TERMINAL_PATH", "")
        self.connected = False

    def _import(self):
        import MetaTrader5 as mt5
        return mt5

    def connect_and_verify_demo(self) -> dict[str, Any]:
        if os.environ.get("EXECUTION_ENV", "demo") != "demo":
            raise RuntimeError("execution env must be demo")
        if not self.server or not self.allowed_server or self.server != self.allowed_server:
            raise RuntimeError("refusing connection: server not on demo allowlist")
        if not self.login or not self.password:
            raise RuntimeError("missing credentials")
        mt5 = self._import()
        kwargs = {"login": int(self.login), "password": self.password, "server": self.server, "timeout": 60000}
        if self.terminal:
            ok = mt5.initialize(self.terminal, **kwargs)
        else:
            ok = mt5.initialize(**kwargs)
        if not ok:
            raise RuntimeError(f"initialize failed: {mt5.last_error()}")
        acct = mt5.account_info()
        if acct is None:
            mt5.shutdown()
            raise RuntimeError("account info unavailable")
        explicit_demo = getattr(acct, "trade_mode", None) is not None and str(getattr(acct, "trade_mode")) in {"0", "ACCOUNT_TRADE_MODE_DEMO"}
        if not explicit_demo:
            mt5.shutdown()
            raise RuntimeError("could not positively prove demo account")
        self.connected = True
        return {"login": acct.login, "server": acct.server, "trade_allowed": acct.trade_allowed}

    @staticmethod
    def _state_name(mt5: Any, value: Any) -> str:
        names = (
            "TRADE_ORDER_STATE_STARTED",
            "TRADE_ORDER_STATE_PLACED",
            "TRADE_ORDER_STATE_CANCELED",
            "TRADE_ORDER_STATE_PARTIAL",
            "TRADE_ORDER_STATE_FILLED",
            "TRADE_ORDER_STATE_REJECTED",
            "TRADE_ORDER_STATE_EXPIRED",
            "TRADE_ORDER_STATE_REQUEST_ADD",
            "TRADE_ORDER_STATE_REQUEST_MODIFY",
            "TRADE_ORDER_STATE_REQUEST_CANCEL",
        )
        for name in names:
            if getattr(mt5, name, object()) == value:
                return name
        return str(value)

    def snapshot(self) -> BrokerSnapshot:
        """Return normalized point-in-time broker truth; never synthesizes fills."""
        if not self.connected:
            raise RuntimeError("MT5 gateway is not connected")
        mt5 = self._import()
        captured_at = datetime.now(timezone.utc).isoformat()

        raw_orders = mt5.orders_get()
        if raw_orders is None:
            raise RuntimeError(f"orders_get failed: {mt5.last_error()}")
        orders: list[BrokerOrderTruth] = []
        for order in raw_orders:
            ticket = str(getattr(order, "ticket", ""))
            comment = str(getattr(order, "comment", "") or "")
            # An absent client id is intentionally preserved as empty; reconciliation
            # will treat it as drift rather than guessing an identity.
            client_order_id = comment if comment.startswith("AG-") else ""
            initial = Decimal(str(getattr(order, "volume_initial", 0)))
            current = Decimal(str(getattr(order, "volume_current", 0)))
            filled = max(Decimal("0"), initial - current)
            orders.append(
                BrokerOrderTruth(
                    broker_order_id=ticket,
                    client_order_id=client_order_id,
                    instrument=str(getattr(order, "symbol", "")),
                    state=self._state_name(mt5, getattr(order, "state", "")),
                    filled_quantity=filled,
                )
            )

        raw_positions = mt5.positions_get()
        if raw_positions is None:
            raise RuntimeError(f"positions_get failed: {mt5.last_error()}")
        by_instrument: dict[str, Decimal] = {}
        buy_type = getattr(mt5, "POSITION_TYPE_BUY", 0)
        for position in raw_positions:
            instrument = str(getattr(position, "symbol", ""))
            volume = Decimal(str(getattr(position, "volume", 0)))
            direction = Decimal("1") if getattr(position, "type", None) == buy_type else Decimal("-1")
            by_instrument[instrument] = by_instrument.get(instrument, Decimal("0")) + direction * volume
        positions = tuple(
            BrokerPositionTruth(instrument, quantity)
            for instrument, quantity in sorted(by_instrument.items())
        )
        return BrokerSnapshot(tuple(orders), positions, captured_at)

    def confirmed_deals(self, date_from: Any, date_to: Any, *, group: str | None = None) -> tuple[BrokerDealRecord, ...]:
        """Return actual broker execution deals through the same connected MT5 session."""
        if not self.connected:
            raise RuntimeError("MT5 gateway is not connected")
        return MT5DealCollector(self._import()).collect(date_from, date_to, group=group)

    def shutdown(self):
        if self.connected:
            self._import().shutdown()
            self.connected = False
