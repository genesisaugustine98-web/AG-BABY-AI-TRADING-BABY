"""Cached executable-data replication for the selected USDJPY H.10 hypothesis."""
from __future__ import annotations
import argparse, hashlib, json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from scripts.replicate_usdjpy_on_dukascopy import MAX_WORKERS, _hour_url, build_candidate_rows, decode_hour, load_h10_release_values, summarize

RETRIES = 4
TIMEOUT = 20
USER_AGENT = "AG-BABY-research/1.0"

def first_at_or_after(ticks, timestamp: datetime):
    for tick in ticks:
        if tick.timestamp >= timestamp:
            return tick
    return None

def market_days(rows: list) -> list[date]:
    out = set()
    for i, row in enumerate(rows):
        if row.high_regime and row.signal and i + 5 < len(rows):
            out.add(row.release_date); out.add(rows[i + 5].release_date)
    return sorted(out)

def fetch_bucket(day: date, hour_utc: int):
    url = _hour_url(day, hour_utc)
    for attempt in range(RETRIES):
        try:
            req = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(req, timeout=TIMEOUT) as response:
                raw = response.read()
            sha = hashlib.sha256(raw).hexdigest()
            return day, ([] if not raw else decode_hour(raw, day, hour_utc)), url, sha, None
        except HTTPError as exc:
            if exc.code == 404:
                return day, [], url, "", "HTTP 404: historical bucket unavailable"
            if exc.code not in {429, 500, 502, 503, 504} or attempt + 1 == RETRIES:
                return day, [], url, "", f"HTTP {exc.code}: {exc.reason}"
        except (URLError, TimeoutError) as exc:
            if attempt + 1 == RETRIES:
                return day, [], url, "", str(exc)
        if attempt + 1 < RETRIES:
            sleep(min(2 ** attempt, 8))
    return day, [], url, "", "unknown fetch failure"

def load_quotes(rows: list, latencies: list[int]):
    by_day = {r.release_date: r for r in rows}; days = market_days(rows)
    buckets = {}; errors = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(fetch_bucket, day, by_day[day].release_at.hour): day for day in days}
        for future in as_completed(futures):
            day, ticks, url, sha, error = future.result()
            if error and "404" not in error: errors[day.isoformat()] = error
            if not error or "404" in error: buckets[day] = (ticks, url, sha)
    quotes = {lat: {} for lat in latencies}; provenance = {}
    for lat in latencies:
        for day, bucket in buckets.items():
            ticks, url, sha = bucket; row = by_day[day]
            tick = first_at_or_after(ticks, row.release_at + timedelta(seconds=lat))
            provenance[f"{day.isoformat()}@{lat}"] = {"url": url, "raw_sha256": sha}
            if tick is not None: quotes[lat][day] = tick
    return quotes, provenance, errors

def execute(rows: list, quotes: dict, provenance: dict, slip_bps: Decimal, latency: int):
    slip = slip_bps / Decimal("10000"); records = []
    for i, row in enumerate(rows):
        if not row.high_regime or not row.signal or i + 5 >= len(rows): continue
        target = rows[i + 5]; entry = quotes.get(row.release_date); exit_tick = quotes.get(target.release_date)
        if entry is None or exit_tick is None: continue
        if row.signal > 0:
            entry_px = entry.ask * (Decimal("1") + slip); exit_px = exit_tick.bid * (Decimal("1") - slip); ret = exit_px / entry_px - Decimal("1")
        else:
            entry_px = entry.bid * (Decimal("1") - slip); exit_px = exit_tick.ask * (Decimal("1") + slip); ret = entry_px / exit_px - Decimal("1")
        records.append({"entry_date":row.release_date.isoformat(),"target_date":target.release_date.isoformat(),"signal":row.signal,"latency_seconds":latency,"entry_time_utc":entry.timestamp.isoformat(),"exit_time_utc":exit_tick.timestamp.isoformat(),"entry_bid":str(entry.bid),"entry_ask":str(entry.ask),"exit_bid":str(exit_tick.bid),"exit_ask":str(exit_tick.ask),"entry_spread":str(entry.ask-entry.bid),"exit_spread":str(exit_tick.ask-exit_tick.bid),"return":str(ret),"provenance_entry":provenance.get(f"{row.release_date.isoformat()}@{latency}",{}),"provenance_exit":provenance.get(f"{target.release_date.isoformat()}@{latency}",{})})
    return records

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("--h10-dir",default="artifacts/h10/vintages"); p.add_argument("--output-dir",default="artifacts/usdjpy_executable"); p.add_argument("--from-date",default="2011-01-01"); p.add_argument("--to-date",default="2026-09-30"); p.add_argument("--latencies",default="0,30,60,300"); p.add_argument("--slippage-bps",default="0,1,2,5"); a=p.parse_args()
    values=load_h10_release_values(Path(a.h10_dir)); rows=build_candidate_rows(values); start,end=date.fromisoformat(a.from_date),date.fromisoformat(a.to_date); rows=[r for r in rows if start<=r.release_date<=end]
    latencies=[int(x) for x in a.latencies.split(",") if x.strip()]; slips=[Decimal(x) for x in a.slippage_bps.split(",") if x.strip()]
    quotes_by_latency,provenance,errors=load_quotes(rows,latencies); results=[]
    for lat in latencies:
        for slip in slips:
            recs=execute(rows,quotes_by_latency[lat],provenance,slip,lat); results.append({"latency_seconds":lat,"extra_slippage_bps_per_side":str(slip),"summary":summarize(recs),"records":recs})
    report={"schema_version":"1","experiment":"usdjpy_h10_high_vol_5release_momentum_executable_replication_v2","data_source":"Dukascopy historical bid/ask tick feed","h10_basis":"validated Federal Reserve H.10 point-in-time release archive","candidate_rule":{"instrument":"USDJPY","state":"20-release realized-volatility high regime","threshold":"median of preceding 104 release-state volatilities; minimum 52 states","signal":"5-release momentum using consecutive H.10 release states"},"execution_model":{"long":"buy ask at entry, sell bid at exit","short":"sell bid at entry, buy ask at exit","latencies_seconds":latencies,"extra_slippage_bps_per_side":[str(x) for x in slips]},"h10_release_count":len(rows),"high_regime_signal_count":sum(1 for r in rows if r.high_regime and r.signal),"unique_market_days_requested":len(market_days(rows)),"market_data_errors":errors,"results":results}
    out=Path(a.output_dir); out.mkdir(parents=True,exist_ok=True); (out/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"h10_release_count":len(rows),"signal_count":report["high_regime_signal_count"],"unique_market_days":report["unique_market_days_requested"],"market_data_errors":len(errors),"configurations":len(results),"configs_with_trades":sum(1 for r in results if r["summary"]["n"]>0)},sort_keys=True)); return 0

if __name__ == "__main__": raise SystemExit(main())
