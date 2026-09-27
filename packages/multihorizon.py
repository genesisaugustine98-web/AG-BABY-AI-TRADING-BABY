"""Multi-horizon signal primitives.

The module intentionally avoids pretending that more indicators equal more independent
evidence. Signals are grouped by economic mechanism and combined only after redundancy
penalties are applied.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from math import sqrt
from typing import Mapping


D0 = Decimal("0")
D1 = Decimal("1")


@dataclass(frozen=True)
class Signal:
    name: str
    mechanism: str
    score: Decimal
    confidence: Decimal
    horizon_seconds: int

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.mechanism.strip():
            raise ValueError("signal name and mechanism are required")
        if not self.score.is_finite() or self.score < -D1 or self.score > D1:
            raise ValueError("signal score must be in [-1,1]")
        if not self.confidence.is_finite() or self.confidence < D0 or self.confidence > D1:
            raise ValueError("signal confidence must be in [0,1]")
        if self.horizon_seconds < 1:
            raise ValueError("horizon_seconds must be positive")


@dataclass(frozen=True)
class CompositeSignal:
    score: Decimal
    confidence: Decimal
    mechanism_weights: Mapping[str, Decimal]
    component_names: tuple[str, ...]
    effective_components: int


def _clamp(value: Decimal) -> Decimal:
    return max(-D1, min(D1, value))


def compose_signals(
    signals: tuple[Signal, ...],
    *,
    mechanism_weights: Mapping[str, Decimal] | None = None,
    mechanism_cap: Decimal = Decimal("0.45"),
) -> CompositeSignal:
    """Combine evidence by mechanism, not raw indicator count.

    Each mechanism contributes a bounded amount. This is deliberately conservative:
    redundancy should reduce, rather than inflate, conviction.
    """
    if mechanism_cap <= 0 or mechanism_cap > 1:
        raise ValueError("mechanism_cap must be in (0,1]")
    if not signals:
        return CompositeSignal(D0, D0, {}, (), 0)

    requested = mechanism_weights or {}
    buckets: dict[str, list[Signal]] = {}
    for signal in signals:
        buckets.setdefault(signal.mechanism, []).append(signal)

    weights: dict[str, Decimal] = {}
    numer = D0
    denom = D0
    for mechanism, members in sorted(buckets.items()):
        base = Decimal(str(requested.get(mechanism, Decimal("1"))))
        if base < D0:
            raise ValueError("mechanism weights cannot be negative")
        # Multiple signals in one mechanism are averaged, not summed.
        signed = sum((m.score * m.confidence for m in members), D0) / Decimal(len(members))
        confidence = sum((m.confidence for m in members), D0) / Decimal(len(members))
        contribution = _clamp(signed) * min(mechanism_cap, base)
        weights[mechanism] = min(mechanism_cap, base)
        numer += contribution
        denom += min(mechanism_cap, base) * max(D0, confidence)

    score = _clamp(numer / denom) if denom > D0 else D0
    mean_conf = sum(
        (s.confidence for s in signals), D0
    ) / Decimal(len(signals))
    # Effective component count discounts duplicate mechanisms.
    effective = len(buckets)
    return CompositeSignal(
        score=score,
        confidence=max(D0, min(D1, mean_conf)),
        mechanism_weights=weights,
        component_names=tuple(s.name for s in signals),
        effective_components=effective,
    )


def realized_volatility(returns: tuple[Decimal, ...]) -> Decimal:
    """Sample standard deviation without external numerical dependencies."""
    if len(returns) < 2:
        raise ValueError("at least two returns are required")
    mean = sum(returns, D0) / Decimal(len(returns))
    variance = sum((r - mean) ** 2 for r in returns) / Decimal(len(returns) - 1)
    return max(D0, variance).sqrt()


__all__ = ["Signal", "CompositeSignal", "compose_signals", "realized_volatility"]
