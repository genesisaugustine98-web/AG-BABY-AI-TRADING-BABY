"""Small standard-library HTTP adapters for free/public research sources.

These adapters are for research and market observation, not direct capital execution.
They record response provenance and hashes so later research can distinguish source
changes from model changes.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def redact_url_credentials(url: str) -> str:
    """Do not persist/log query parameters that may contain API keys."""
    return url.split("?", 1)[0]


@dataclass(frozen=True)
class SourceSnapshot:
    source_id: str
    url: str
    fetched_at_ms: int
    sha256: str
    payload: Any


class PublicHttpClient:
    def __init__(self, *, timeout_seconds: float = 10.0, user_agent: str = "AG-BABY-free-stack/1.0") -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent

    def get_json(self, url: str, *, params: dict[str, Any] | None = None) -> SourceSnapshot:
        full_url = url
        if params:
            encoded = urlencode({k: v for k, v in params.items() if v is not None})
            full_url = f"{url}{'&' if '?' in url else '?'}{encoded}"
        request = Request(full_url, headers={"User-Agent": self.user_agent, "Accept": "application/json"})
        with urlopen(request, timeout=self.timeout_seconds) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024:
            raise RuntimeError("source payload exceeds safety limit")
        payload = json.loads(raw.decode("utf-8"))
        return SourceSnapshot(
            source_id="http-json",
            url=redact_url_credentials(full_url),
            fetched_at_ms=int(time.time() * 1000),
            sha256=sha256(raw).hexdigest(),
            payload=payload,
        )


class BinancePublicClient:
    """Public Binance spot market-data adapter; no account credentials."""
    BASE_URL = "https://api.binance.com"

    def __init__(self, client: PublicHttpClient | None = None) -> None:
        self.client = client or PublicHttpClient()

    def ticker(self, symbol: str) -> SourceSnapshot:
        symbol = symbol.strip().upper()
        if not symbol:
            raise ValueError("symbol is required")
        return self.client.get_json(
            f"{self.BASE_URL}/api/v3/ticker/bookTicker",
            params={"symbol": symbol},
        )

    def klines(self, symbol: str, interval: str = "1h", limit: int = 500) -> SourceSnapshot:
        if not symbol.strip():
            raise ValueError("symbol is required")
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")
        return self.client.get_json(
            f"{self.BASE_URL}/api/v3/klines",
            params={"symbol": symbol.strip().upper(), "interval": interval, "limit": limit},
        )


class KrakenFuturesPublicClient:
    """Public Kraken Futures analytics/candles adapter."""
    BASE_URL = "https://futures.kraken.com/api/charts/v1"
    ANALYTICS_PATH = "analytics"

    def __init__(self, client: PublicHttpClient | None = None) -> None:
        self.client = client or PublicHttpClient()

    def candles(self, symbol: str, resolution: str = "1h", count: int = 200) -> SourceSnapshot:
        if not symbol.strip():
            raise ValueError("symbol is required")
        if count < 1 or count > 5000:
            raise ValueError("count must be between 1 and 5000")
        return self.client.get_json(
            f"{self.BASE_URL}/trade/{symbol.strip()}/{resolution}",
            params={"count": count},
        )

    def analytics(self, symbol: str, analytics_type: str = "funding", since: int | None = None, interval: int = 3600) -> SourceSnapshot:
        if not symbol.strip() or not analytics_type.strip():
            raise ValueError("symbol and analytics_type are required")
        if interval not in {60, 300, 900, 1800, 3600, 14400, 43200, 86400, 604800}:
            raise ValueError("unsupported Kraken analytics interval")
        params = {"since": since or int(time.time()) - 86400 * 7, "interval": interval}
        return self.client.get_json(
            f"{self.BASE_URL}/{self.ANALYTICS_PATH}/{symbol.strip()}/{analytics_type.strip()}",
            params=params,
        )


class CFTCClient:
    """CFTC public reporting adapter. Normal PRE API use does not require a token."""

    def __init__(self, client: PublicHttpClient | None = None) -> None:
        self.client = client or PublicHttpClient()

    def fetch_url(self, url: str) -> SourceSnapshot:
        if not url.startswith("https://"):
            raise ValueError("CFTC source must use HTTPS")
        snapshot = self.client.get_json(url)
        return SourceSnapshot("cftc-pre", snapshot.url, snapshot.fetched_at_ms, snapshot.sha256, snapshot.payload)


class FREDClient:
    """FRED/ALFRED adapter. Current API requests require a registered API key."""
    BASE_URL = "https://api.stlouisfed.org/fred"

    def __init__(self, api_key: str | None = None, client: PublicHttpClient | None = None) -> None:
        self.api_key = api_key or os.getenv("FRED_API_KEY")
        self.client = client or PublicHttpClient()

    def observations(self, series_id: str, *, start: str | None = None, end: str | None = None, vintage: str | None = None) -> SourceSnapshot:
        if not self.api_key:
            raise RuntimeError("FRED_API_KEY is required for FRED API access")
        if not series_id.strip():
            raise ValueError("series_id is required")
        params: dict[str, Any] = {
            "series_id": series_id.strip(),
            "api_key": self.api_key,
            "file_type": "json",
            "observation_start": start,
            "observation_end": end,
        }
        if vintage:
            params["realtime_end"] = vintage
            params["realtime_start"] = vintage
        return self.client.get_json(f"{self.BASE_URL}/series/observations", params=params)


__all__ = [
    "SourceSnapshot",
    "PublicHttpClient",
    "BinancePublicClient",
    "KrakenFuturesPublicClient",
    "CFTCClient",
    "FREDClient",
    "redact_url_credentials",
]
