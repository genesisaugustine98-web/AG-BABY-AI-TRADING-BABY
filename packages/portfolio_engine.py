"""Portfolio state aggregation independent of broker adapters."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .models import PortfolioState


@dataclass(frozen=True)
class PositionSnapshot:
    instrument: str
    net_quantity: Decimal
    strategy_id: str | None = None


@dataclass(frozen=True)
class PortfolioSnapshot:
    captured_at_ms: int
    equity: Decimal
    balance: Decimal
    daily_pnl: Decimal
    drawdown_fraction: Decimal
    gross_risk_fraction: Decimal
    strategy_risk_fraction: Decimal
    open_positions: int
    frozen: bool


class PortfolioEngine:
    """Tracks broker-authoritative account/position facts and explicit risk reservations."""

    def __init__(self, *, initial_equity: Decimal | None = None) -> None:
        self._balance = Decimal("0")
        self._equity = Decimal("0")
        self._day_start_equity = initial_equity if initial_equity is not None else Decimal("0")
        self._peak_equity = initial_equity if initial_equity is not None else Decimal("0")
        self._positions: dict[str, PositionSnapshot] = {}
        self._reserved_order_risk: dict[str, Decimal] = {}
        self._strategy_risk: dict[str, Decimal] = {}
        self._frozen = True
        self._captured_at_ms = 0

    def update_account(self, *, captured_at_ms: int, balance: Decimal, equity: Decimal) -> None:
        if captured_at_ms <= 0 or balance < 0 or equity < 0:
            raise ValueError("invalid account snapshot")
        if self._captured_at_ms and captured_at_ms < self._captured_at_ms:
            raise ValueError("account snapshot moved backwards")
        self._captured_at_ms = captured_at_ms
        self._balance = balance
        self._equity = equity
        if self._day_start_equity <= 0:
            self._day_start_equity = equity
        self._peak_equity = max(self._peak_equity, equity)
        self._frozen = False

    def update_positions(self, positions: tuple[PositionSnapshot, ...], *, captured_at_ms: int) -> None:
        if captured_at_ms <= 0:
            raise ValueError("captured_at_ms must be positive")
        if self._captured_at_ms and captured_at_ms < self._captured_at_ms:
            raise ValueError("position snapshot moved backwards")
        next_positions: dict[str, PositionSnapshot] = {}
        for position in positions:
            symbol = position.instrument.strip().upper()
            if not symbol:
                raise ValueError("position instrument is required")
            if symbol in next_positions:
                raise ValueError(f"duplicate position instrument:{symbol}")
            next_positions[symbol] = PositionSnapshot(symbol, position.net_quantity, position.strategy_id)
        self._positions = next_positions
        self._captured_at_ms = max(self._captured_at_ms, captured_at_ms)

    def reset_order_risk_reservations(self) -> None:
        self._reserved_order_risk.clear()

    def reset_strategy_risk(self) -> None:
        self._strategy_risk.clear()

    def reserve_order_risk(self, key: str, fraction: Decimal) -> None:
        key = key.strip()
        if not key or fraction < 0 or fraction > Decimal("1"):
            raise ValueError("invalid risk reservation")
        self._reserved_order_risk[key] = fraction

    def release_order_risk(self, key: str) -> None:
        self._reserved_order_risk.pop(key.strip(), None)

    def set_strategy_risk(self, strategy_id: str, fraction: Decimal) -> None:
        strategy_id = strategy_id.strip()
        if not strategy_id or fraction < 0 or fraction > Decimal("1"):
            raise ValueError("invalid strategy risk")
        self._strategy_risk[strategy_id] = fraction

    def freeze(self) -> None:
        self._frozen = True

    def unfreeze(self) -> None:
        if self._captured_at_ms <= 0:
            raise RuntimeError("cannot unfreeze before authoritative account/position data")
        self._frozen = False

    def snapshot(self, *, captured_at_ms: int | None = None) -> PortfolioSnapshot:
        at = captured_at_ms or self._captured_at_ms
        if at <= 0:
            raise RuntimeError("portfolio has no authoritative snapshot")
        daily_pnl = self._equity - self._day_start_equity
        drawdown = Decimal("0") if self._peak_equity <= 0 else max(
            Decimal("0"), Decimal("1") - self._equity / self._peak_equity
        )
        gross = min(Decimal("1"), sum(self._reserved_order_risk.values(), Decimal("0")))
        strategy = min(Decimal("1"), sum(self._strategy_risk.values(), Decimal("0")))
        return PortfolioSnapshot(
            captured_at_ms=at,
            equity=self._equity,
            balance=self._balance,
            daily_pnl=daily_pnl,
            drawdown_fraction=drawdown,
            gross_risk_fraction=gross,
            strategy_risk_fraction=strategy,
            open_positions=sum(1 for p in self._positions.values() if p.net_quantity != 0),
            frozen=self._frozen,
        )

    def as_portfolio_state(self, *, captured_at_ms: int | None = None) -> PortfolioState:
        snap = self.snapshot(captured_at_ms=captured_at_ms)
        return PortfolioState(
            equity=snap.equity,
            daily_pnl=snap.daily_pnl,
            gross_risk_fraction=snap.gross_risk_fraction,
            net_usd_factor=Decimal("0"),
            open_positions=snap.open_positions,
            account_drawdown_fraction=snap.drawdown_fraction,
            strategy_risk_fraction=snap.strategy_risk_fraction,
            frozen=snap.frozen,
        )


__all__ = ["PortfolioEngine", "PortfolioSnapshot", "PositionSnapshot"]
