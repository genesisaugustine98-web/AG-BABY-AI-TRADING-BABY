"""Collect real demo evidence and an explicit optional demo-order ambiguity drill."""
from __future__ import annotations
import argparse,json,os,time,sys
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
REPO_ROOT=Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path: sys.path.insert(0,str(REPO_ROOT))
from apps.execution_gateway.mt5_gateway import DemoOnlyMT5Gateway
from apps.execution_gateway.mt5_event_stream import MT5BrokerOrderEventStream
from apps.execution_gateway.mt5_orders import DemoOnlyMT5OrderAdapter
from apps.execution_gateway.runtime import DemoExecutionRuntime
from apps.trading_runtime.mt5_runtime import MT5RuntimeAdapter
from packages.evidence_protocol import EvidenceClass,EvidencePack,EvidenceStatus
from packages.models import AdmissionContext,EventState,Forecast,MarketState,PortfolioState,TradeIntent
from packages.tsmom_economic import chronological_split_indices,evaluate_split_sensitivity
from packages.tsmom_forecast import TSMOMForecastModel,dataset_fingerprint

class AmbiguousDemoBroker:
    def __init__(self,adapter): self.adapter=adapter
    def submit(self,request): self.adapter.submit(request); raise RuntimeError("INJECTED_CRASH_AFTER_BROKER_SUBMIT")

def strategy(api,symbol,commit):
    from apps.execution_gateway.mt5_market_data import MT5MarketDataAdapter
    rows=list(MT5MarketDataAdapter(api).fetch_completed_bars(symbol=symbol,timeframe="H1",count=20000))
    if len(rows)<500: raise RuntimeError(f"insufficient bars:{symbol}:{len(rows)}")
    fp=dataset_fingerprint(rows); model=TSMOMForecastModel(lookback_bars=24,horizon_bars=6,min_training_samples=30,bar_interval_seconds=3600)
    val=model.fit(rows,dataset_fingerprint=fp,code_commit_sha=commit); splits=chronological_split_indices(len(rows)); costs=(Decimal("0"),Decimal("1"),Decimal("2"),Decimal("5"),Decimal("10"))
    cells={}
    for split in ("validation","holdout"):
        lo,hi=splits[split]; results=evaluate_split_sensitivity(model,rows,split=split,start_index=lo,end_index=hi,one_way_costs_bps=costs,delay_bars=1)
        cells[split]={str(c):{"n":results[c].n,"mean_net":None if results[c].mean_net is None else str(results[c].mean_net),"cumulative_net":None if results[c].cumulative_net is None else str(results[c].cumulative_net),"max_drawdown":None if results[c].max_drawdown is None else str(results[c].max_drawdown),"profit_factor":None if results[c].profit_factor is None else str(results[c].profit_factor),"sharpe_like":None if results[c].sharpe_like is None else str(results[c].sharpe_like)} for c in costs}
    return {"symbol":symbol,"bar_count":len(rows),"dataset_fingerprint":fp,"validation":{"development_n":val.development_n,"validation_n":val.validation_n,"holdout_n":val.holdout_n,"calibration_score":str(val.calibration_score)},"splits":cells}

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--duration-minutes",type=int,default=5)
    ap.add_argument("--interval-seconds",type=int,default=15)
    ap.add_argument("--symbols",default=os.environ.get("AG_SYMBOLS","USDJPY"))
    ap.add_argument("--real-demo-order-drill",action="store_true")
    ap.add_argument("--output",default="artifacts/evidence/demo-evidence.json")
    ap.add_argument("--commit-sha",default=os.environ.get("GITHUB_SHA","unknown"))
    a=ap.parse_args()
    if os.environ.get("EXECUTION_ENV","demo").lower()!="demo": raise SystemExit("EXECUTION_ENV must be demo")
    if a.duration_minutes<1 or a.interval_seconds<1: raise SystemExit("duration and interval must be positive")
    symbols=tuple(dict.fromkeys(x.strip().upper() for x in a.symbols.split(",") if x.strip()))
    gw=DemoOnlyMT5Gateway(); gw.connect_and_verify_demo(); rt=None
    try:
        rt=DemoExecutionRuntime.create(); api=gw.mt5_api(); pack=EvidencePack.create(commit_sha=a.commit_sha)
        required_live = (
            ("demo_24h_soak","continuous demo observation", a.duration_minutes>=1440),
            ("demo_reconciliation_drift","intentional broker/internal mismatch with observed freeze", False),
            ("demo_unknown_recovery","ambiguous demo submission resolved from broker truth", a.real_demo_order_drill),
            ("demo_restart_recovery","fresh process restart followed by clean reconciliation", False),
            ("demo_network_outage","real transport outage drill", False),
            ("demo_database_outage","real database outage drill", False),
        )
        for name, requirement, observed in required_live:
            if not observed:
                pack.add(name=name,evidence_class=EvidenceClass.LIVE_DEMO,status=EvidenceStatus.UNOBSERVED,details={"requirement":requirement})
        started=time.time(); cycles=0; errors=0; events=0
        while time.time()-started < a.duration_minutes*60:
            cycles+=1
            try:
                rt.reconciliation.reconcile_once(); now=int(time.time()*1000); stream=MT5BrokerOrderEventStream(api,environment="demo",checkpoint_store=rt.safety)
                events += len(stream.poll(now_msc=now)); rt.safety.record_account_snapshot(gw.account_snapshot())
            except Exception: errors+=1
            time.sleep(a.interval_seconds)
        soak_name="demo_24h_soak" if a.duration_minutes>=1440 else "demo_soak_observation"
        if soak_name=="demo_24h_soak":
            for idx,row in enumerate(pack.records):
                if row.name=="demo_24h_soak":
                    pack.records[idx]=type(row)(name=row.name,evidence_class=row.evidence_class,status=EvidenceStatus.PASS if cycles and errors==0 else EvidenceStatus.FAIL,observed_at=row.observed_at,details={"duration_minutes":a.duration_minutes,"cycles":cycles,"errors":errors,"broker_order_events":events},artifact=row.artifact,required_for_gate=True)
                    break
        else:
            pack.add(name=soak_name,evidence_class=EvidenceClass.LIVE_DEMO,status=EvidenceStatus.PASS if cycles and errors==0 else EvidenceStatus.FAIL,details={"duration_minutes":a.duration_minutes,"cycles":cycles,"errors":errors,"broker_order_events":events},required_for_gate=False)
        if a.real_demo_order_drill:
            mt5r=MT5RuntimeAdapter(gw); symbol=symbols[0]; now=int(time.time()*1000); q=mt5r.quote(symbol,now_ms=now); spec=mt5r.instrument_spec(symbol); acct=gw.account_snapshot(); qty=spec.min_volume; dist=max(q.mid*Decimal("0.01"),spec.tick_size*10); limit=q.mid-dist*Decimal("2")
            intent=TradeIntent("evidence-"+str(now),"demo-evidence","1","evidence",symbol,"BUY",qty,"LIMIT",limit,limit-dist,limit+dist*2,now,now+300000,Decimal("0.01"),Decimal("0.0001"),300,frozenset())
            ctx=AdmissionContext(now,q,Forecast("evidence","1",now,300,Decimal("0.01"),"fraction",Decimal("0.99"),Decimal("0.99"),Decimal("0.99")),MarketState(EventState.NORMAL,max(0,now-q.event_time_ms),q.spread/q.mid,Decimal("1"),Decimal("0"),Decimal("1"),Decimal("1")),PortfolioState(Decimal(str(acct["equity"])),Decimal("0"),Decimal("0"),Decimal("0"),0,Decimal("0"),Decimal("0"),False),Decimal("0.0001"),Decimal("0"))
            attempt=rt.kernel.execute(intent=intent,context=ctx,instrument=spec,repository=rt.orders,broker=AmbiguousDemoBroker(DemoOnlyMT5OrderAdapter(api)))
            recovered=rt.recover(order_id=attempt.order_id,client_order_id=attempt.client_order_id) if attempt.order_id else None
            status=EvidenceStatus.PASS if attempt.decision=="UNKNOWN" and recovered and recovered.outcome=="ACCEPTED" else EvidenceStatus.FAIL
            for idx,row in enumerate(pack.records):
                if row.name=="demo_unknown_recovery":
                    pack.records[idx]=type(row)(name=row.name,evidence_class=row.evidence_class,status=status,observed_at=row.observed_at,details={"initial":attempt.decision,"recovery":None if recovered is None else recovered.outcome,"broker_order_id":None if recovered is None else recovered.broker_order_id},artifact=row.artifact,required_for_gate=True)
                    break
            if recovered and recovered.broker_order_id:
                cleanup=rt.cancel_order(order_id=attempt.order_id); pack.add(name="demo_order_drill_cleanup",evidence_class=EvidenceClass.LIVE_DEMO,status=EvidenceStatus.PASS if cleanup.allowed else EvidenceStatus.FAIL,details={"cancel":None if cleanup.result is None else cleanup.result.outcome},required_for_gate=False)
        if a.duration_minutes<1440:
            pack.add(name="demo_24h_soak_remaining",evidence_class=EvidenceClass.LIVE_DEMO,status=EvidenceStatus.UNOBSERVED,details={"requirement":"run this collector with --duration-minutes 1440"},required_for_gate=False)
        strat={}
        for s in symbols:
            try: strat[s]=strategy(api,s,a.commit_sha)
            except Exception as exc: strat[s]={"error":f"{type(exc).__name__}:{exc}"}
        pack.add(name="strategy_validation",evidence_class=EvidenceClass.HISTORICAL,status=EvidenceStatus.PASS if all("error" not in x for x in strat.values()) else EvidenceStatus.FAIL,details={"symbols":strat})
        pack.write_json(a.output); print(json.dumps(pack.summary(),indent=2,sort_keys=True)); return 0
    finally:
        if rt: rt.close()
        gw.shutdown()

if __name__=="__main__": raise SystemExit(main())
