"""Wire public/free observations into AG-BABY's canonical research contract.

This adapter creates compact, normalized research snapshots from public market sources.
It never creates executable FX quotes and never has broker credentials.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .data_contract import MarketObservation
from .free_stack_sources import BinancePublicClient, KrakenFuturesPublicClient, SourceSnapshot


@dataclass(frozen=True)
class AdapterResult:
    source_id: str
    instrument: str
    observation: MarketObservation | None
    snapshot_sha256: str
    status: str
    reason: str


def _ms(value: Any) -> int:
    return int(value)


def _binance_observation(snap: SourceSnapshot, symbol: str) -> MarketObservation:
    payload = snap.payload
    bid = Decimal(str(payload["bidPrice"]))
    ask = Decimal(str(payload["askPrice"]))
    # Public book-ticker responses do not provide an independent event timestamp.
    # Use fetch time as the observation event/usable boundary; this is explicitly
    # labeled as provider-observation time rather than exchange event time.
    event_ms = snap.fetched_at_ms
    return MarketObservation(
        instrument=symbol,
        event_time=_datetime_from_ms(event_ms),
        usable_at=_datetime_from_ms(event_ms),
        open=(bid + ask) / Decimal("2"),
        high=(bid + ask) / Decimal("2"),
        low=(bid + ask) / Decimal("2"),
        close=(bid + ask) / Decimal("2"),
        source="binance_public_book_ticker",
        source_version="api-v3-bookTicker",
        observation_id=f"binance:{symbol}:{event_ms}:{snap.sha256[:16]}",
    )


def _datetime_from_ms(ms: int):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def _kraken_funding_observation(snap: SourceSnapshot, symbol: str) -> MarketObservation | None:
    payload = snap.payload
    # Kraken analytics response shapes can evolve. Only accept the common
    # list-of-series shape when a numeric latest value can be unambiguously identified.
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list) or not data:
        return None
    latest = data[-1]
    if isinstance(latest, dict):
        raw = latest.get("fundingRate", latest.get("funding_rate", latest.get("value")))
        raw_time = latest.get("time", latest.get("timestamp"))
    elif isinstance(latest, (list, tuple)) and len(latest) >= 2:
        raw_time, raw = latest[0], latest[-1]
    else:
        return None
    if raw is None:
        return None
    try:
        value = Decimal(str(raw))
    except Exception:
        return None
    try:
        event_ms = _ms(raw_time) if raw_time is not None else snap.fetched_at_ms
        if event_ms < 10_000_000_000:
            event_ms *= 1000
    except Exception:
        event_ms = snap.fetched_at_ms
    return MarketObservation(
        instrument=symbol,
        event_time=_datetime_from_ms(event_ms),
        usable_at=_datetime_from_ms(snap.fetched_at_ms),
        open=value,
        high=value,
        low=value,
        close=value,
        source="kraken_futures_funding",
        source_version="charts-v1-analytics",
        observation_id=f"kraken:{symbol}:{event_ms}:{snap.sha256[:16]}",
    )


class FreeStackResearchAdapter:
    """Collect and normalize non-broker observations for the research plane."""

    def __init__(
        self,
        *,
        binance: BinancePublicClient | None = None,
        kraken: KrakenFuturesPublicClient | None = None,
    ) -> None:
        self.binance = binance or BinancePublicClient()
        self.kraken = kraken or KrakenFuturesPublicClient()

    def collect(self, *, binance_symbol: str = "BTCUSDT", kraken_symbol: str = "PI_XBTUSD") -> tuple[AdapterResult, ...]:
        results: list[AdapterResult] = []
        try:
            snap = self.binance.ticker(binance_symbol)
            results.append(AdapterResult(
                "BINANCE_PUBLIC",
                binance_symbol.upper(),
                _binance_observation(snap, binance_symbol.upper()),
                snap.sha256,
                "ok",
                "public book ticker normalized",
            ))
        except Exception as exc:
            results.append(AdapterResult("BINANCE_PUBLIC", binance_symbol.upper(), None, "", "error", type(exc).__name__))

        try:
            snap = self.kraken.analytics(kraken_symbol, "funding", interval=3600)
            observation = _kraken_funding_observation(snap, kraken_symbol.upper())
            results.append(AdapterResult(
                "KRAKEN_FUTURES_ANALYTICS",
                kraken_symbol.upper(),
                observation,
                snap.sha256,
                "ok" if observation else "unusable",
                "funding observation normalized" if observation else "analytics response shape not recognized",
            ))
        except Exception as exc:
            results.append(AdapterResult("KRAKEN_FUTURES_ANALYTICS", kraken_symbol.upper(), None, "", "error", type(exc).__name__))

        return tuple(results)


__all__ = ["AdapterResult", "FreeStackResearchAdapter"]
