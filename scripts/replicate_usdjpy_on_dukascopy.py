"""Executable-data replication of the selected USDJPY H.10 conditional hypothesis.

Research-only: downloads Dukascopy historical bid/ask tick buckets around the exact
Federal Reserve H.10 release clock, then evaluates the pre-specified
high-volatility / 5-release USDJPY momentum rule with real bid/ask execution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import lzma
import math
import re
import struct
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, getcontext
from pathlib import Path
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

getcontext().prec = 40

DUKA_BASE = "https://datafeed.dukascopy.com/datafeed"
NY = ZoneInfo("America/New_York")
RECORD = struct.Struct(">IIIff")
JPY_SCALE = 1000
MAX_WORKERS = 4
RETRIES = 6
REQUEST_TIMEOUT = 30
USER_AGENT = "AG-BABY-research/1.0"


@dataclass(frozen=True)
class Tick:
    timestamp: datetime
    ask: Decimal
    bid: Decimal
    ask_volume: float
    bid_volume: float


@dataclass(frozen=True)
class ReleaseRow:
    release_date: date
    release_at: datetime
    value: Decimal
    prior_value: Decimal | None
    prior_return: Decimal | None
    volatility: Decimal | None
    threshold: Decimal | None
    high_regime: bool
    signal: int


def release_at(release_date: date) -> datetime:
    return datetime.combine(release_date, datetime.min.time(), tzinfo=NY).replace(
        hour=16, minute=15
    ).astimezone(timezone.utc)


def _float_decimal(value: str) -> Decimal:
    return Decimal(value.strip())


def load_h10_rows(root: Path) -> dict[date, Decimal]:
    """Load USDJPY H.10 values from the validated dated-release JSONL archive."""
    out: dict[date, Decimal] = {}
    for path in sorted(root.glob("h10_release_*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("instrument") != "USDJPY_REFERENCE":
                continue
            day = date.fromisoformat(str(row["event_time"])[:10])
            out[day] = _float_decimal(str(row["value"]))
    return out


def _rolling_volatility(log_returns: list[Decimal], window: int) -> Decimal | None:
    if len(log_returns) < window:
        return None
    sample = log_returns[-window:]
    mean = sum(sample, Decimal("0")) / Decimal(window)
    variance = sum((x - mean) ** 2 for x in sample) / Decimal(window)
    return variance.sqrt()


def _median(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / Decimal("2")


def build_candidate_rows(values: dict[date, Decimal], *, vol_window: int = 20, threshold_window: int = 104) -> list[ReleaseRow]:
    dates = sorted(values)
    rows: list[ReleaseRow] = []
    returns_by_date: dict[date, Decimal] = {}
    for i in range(1, len(dates)):
        prev = values[dates[i - 1]]
        cur = values[dates[i]]
        if prev <= 0 or cur <= 0:
            continue
        returns_by_date[dates[i]] = (cur / prev).ln()

    vols_by_date: dict[date, Decimal] = {}
    for i, day in enumerate(dates):
        prior_returns = [returns_by_date[d] for d in dates[max(0, i - vol_window + 1) : i + 1] if d in returns_by_date]
        vol = _rolling_volatility(prior_returns, vol_window)
        if vol is not None:
            vols_by_date[day] = vol

    for i, day in enumerate(dates):
        if i == 0:
            continue
        prev_day = dates[i - 1]
        prior_return = returns_by_date.get(day)
        vol = vols_by_date.get(day)
        preceding_vols = [vols_by_date[d] for d in dates[:i] if d in vols_by_date]
        threshold_values = preceding_vols[-threshold_window:]
        threshold = _median(threshold_values) if len(threshold_values) >= 52 else None
        high = vol is not None and threshold is not None and vol > threshold
        signal = 1 if (high and prior_return is not None and prior_return > 0) else -1 if (high and prior_return is not None and prior_return < 0) else 0
        rows.append(
            ReleaseRow(
                release_date=day,
                release_at=release_at(day),
                value=values[day],
                prior_value=values[prev_day],
                prior_return=prior_return,
                volatility=vol,
                threshold=threshold,
                high_regime=high,
                signal=signal,
            )
        )
    return rows


def _hour_url(day: date, hour_utc: int) -> str:
    return f"{DUKA_BASE}/USDJPY/{day.year:04d}/{day.month - 1:02d}/{day.day:02d}/{hour_utc:02d}h_ticks.bi5"


def fetch_bytes(url: str) -> bytes:
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=REQUEST_TIMEOUT) as response:
                return response.read()
        except (HTTPError, URLError, TimeoutError) as exc:
            last = exc
            if attempt + 1 < RETRIES:
                sleep(min(2 ** attempt, 20))
    assert last is not None
    raise last


def decode_hour(raw: bytes, day: date, hour_utc: int) -> list[Tick]:
    if not raw:
        return []
    data = lzma.decompress(raw)
    if len(data) % RECORD.size:
        raise ValueError(f"invalid BI5 payload length: {len(data)}")
    start = datetime(day.year, day.month, day.day, hour_utc, tzinfo=timezone.utc)
    ticks: list[Tick] = []
    for offset in range(0, len(data), RECORD.size):
        ms, ask_raw, bid_raw, ask_volume, bid_volume = RECORD.unpack_from(data, offset)
        ts = start + timedelta(milliseconds=ms)
        ticks.append(
            Tick(
                timestamp=ts,
                ask=Decimal(ask_raw) / Decimal(JPY_SCALE),
                bid=Decimal(bid_raw) / Decimal(JPY_SCALE),
                ask_volume=ask_volume,
                bid_volume=bid_volume,
            )
        )
    return ticks


def fetch_release_tick(day: date, timestamp: datetime) -> tuple[Tick | None, str | None, str | None]:
    url = _hour_url(day, timestamp.hour)
    try:
        raw = fetch_bytes(url)
    except Exception:
        return None, url, None
    if not raw:
        return None, url, hashlib.sha256(raw).hexdigest()
    ticks = decode_hour(raw, day, timestamp.hour)
    for tick in ticks:
        if tick.timestamp >= timestamp:
            return tick, url, hashlib.sha256(raw).hexdigest()
    return None, url, hashlib.sha256(raw).hexdigest()


def _split_dates(rows: list[ReleaseRow], start: date, end: date) -> list[ReleaseRow]:
    return [row for row in rows if start <= row.release_date <= end]


def execute_replication(rows: list[ReleaseRow], *, latency_seconds: int, extra_slippage_bps: Decimal) -> list[dict[str, object]]:
    active = [r for r in rows if r.high_regime and r.signal != 0]
    by_date = {r.release_date: r for r in rows}
    tasks: dict[date, datetime] = {}
    for row in active:
        target_idx = rows.index(row) + 5
        if target_idx >= len(rows):
            continue
        target = rows[target_idx]
        tasks[row.release_date] = row.release_at + timedelta(seconds=latency_seconds)
        tasks[target.release_date] = target.release_at + timedelta(seconds=latency_seconds)

    quotes: dict[date, Tick] = {}
    provenance: dict[str, dict[str, str | None]] = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {
            executor.submit(fetch_release_tick, day, ts): (day, ts)
            for day, ts in tasks.items()
        }
        for future in as_completed(future_map):
            day, _ = future_map[future]
            tick, url, raw_sha = future.result()
            provenance[str(day)] = {"url": url, "raw_sha256": raw_sha}
            if tick is not None:
                quotes[day] = tick

    rows_out: list[dict[str, object]] = []
    slippage_rate = extra_slippage_bps / Decimal("10000")
    for row in active:
        idx = rows.index(row)
        if idx + 5 >= len(rows):
            continue
        target = rows[idx + 5]
        entry = quotes.get(row.release_date)
        exit_tick = quotes.get(target.release_date)
        if entry is None or exit_tick is None:
            continue
        if row.signal > 0:
            entry_price = entry.ask * (Decimal("1") + slippage_rate)
            exit_price = exit_tick.bid * (Decimal("1") - slippage_rate)
            ret = exit_price / entry_price - Decimal("1")
        else:
            entry_price = entry.bid * (Decimal("1") - slippage_rate)
            exit_price = exit_tick.ask * (Decimal("1") + slippage_rate)
            ret = entry_price / exit_price - Decimal("1")
        spread_entry = entry.ask - entry.bid
        spread_exit = exit_tick.ask - exit_tick.bid
        rows_out.append(
            {
                "entry_date": row.release_date.isoformat(),
                "target_date": target.release_date.isoformat(),
                "entry_time_utc": entry.timestamp.isoformat(),
                "exit_time_utc": exit_tick.timestamp.isoformat(),
                "signal": row.signal,
                "h10_volatility": None if row.volatility is None else str(row.volatility),
                "h10_threshold": None if row.threshold is None else str(row.threshold),
                "entry_bid": str(entry.bid),
                "entry_ask": str(entry.ask),
                "exit_bid": str(exit_tick.bid),
                "exit_ask": str(exit_tick.ask),
                "entry_spread": str(spread_entry),
                "exit_spread": str(spread_exit),
                "return": str(ret),
                "provenance_entry": provenance.get(str(row.release_date), {}),
                "provenance_exit": provenance.get(str(target.release_date), {}),
            }
        )
    return rows_out


def summarize(records: list[dict[str, object]]) -> dict[str, object]:
    if not records:
        return {"n": 0, "mean_return": None, "median_return": None, "win_rate": None, "sum_return": None}
    values = [Decimal(str(r["return"])) for r in records]
    wins = sum(1 for x in values if x > 0)
    return {
        "n": len(values),
        "mean_return": str(sum(values, Decimal("0")) / Decimal(len(values))),
        "median_return": str(_median(values)),
        "win_rate": str(Decimal(wins) / Decimal(len(values))),
        "sum_return": str(sum(values, Decimal("0"))),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--h10-dir", default="artifacts/h10/vintages")
    parser.add_argument("--output-dir", default="artifacts/usdjpy_executable")
    parser.add_argument("--from-date", default="2011-01-01")
    parser.add_argument("--to-date", default="2026-09-30")
    parser.add_argument("--latencies", default="0,30,60,300")
    parser.add_argument("--slippage-bps", default="0,1,2,5")
    args = parser.parse_args()

    h10_dir = Path(args.h10_dir)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    values = load_h10_rows(h10_dir)
    rows = build_candidate_rows(values)
    start = date.fromisoformat(args.from_date)
    end = date.fromisoformat(args.to_date)
    rows = _split_dates(rows, start, end)

    all_results: list[dict[str, object]] = []
    for latency in [int(x) for x in args.latencies.split(",") if x.strip()]:
        # Fetch quotes once per latency; timestamp changes with latency, so each must be separate.
        for slip_text in [x for x in args.slippage_bps.split(",") if x.strip()]:
            slip = Decimal(slip_text)
            records = execute_replication(rows, latency_seconds=latency, extra_slippage_bps=slip)
            all_results.append({
                "latency_seconds": latency,
                "extra_slippage_bps_per_side": str(slip),
                "summary": summarize(records),
                "records": records,
            })

    report = {
        "schema_version": "1",
        "experiment": "usdjpy_h10_high_vol_5release_momentum_executable_replication_v1",
        "data_source": "Dukascopy historical bid/ask tick feed",
        "source_basis": "provider-published historical quotes; not a claim of proprietary institutional flow",
        "h10_basis": "validated Federal Reserve H.10 point-in-time release archive",
        "candidate_rule": {
            "instrument": "USDJPY",
            "state": "20-release realized-volatility high regime",
            "threshold": "median of preceding 104 release-state volatilities; minimum 52 states",
            "signal": "5-release momentum",
        },
        "execution_model": {
            "long": "buy ask at entry, sell bid at exit",
            "short": "sell bid at entry, buy ask at exit",
            "extra_slippage_tested_bps_per_side": [x for x in args.slippage_bps.split(",") if x.strip()],
            "latencies_seconds": [int(x) for x in args.latencies.split(",") if x.strip()],
        },
        "h10_release_count": len(rows),
        "high_regime_signal_count": sum(1 for r in rows if r.high_regime and r.signal != 0),
        "results": all_results,
    }
    (out / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps({
        "h10_release_count": len(rows),
        "high_regime_signal_count": report["high_regime_signal_count"],
        "configurations": len(all_results),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
