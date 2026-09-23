"""Intentional real-demo reconciliation-drift drill with clean recovery.

A far-away pending order is created normally. The broker-side order is then
cancelled out-of-band through the MT5 API. Reconciliation must detect the
durable-order/broker mismatch, persist a freeze, and refuse trading. The drill
then records the externally confirmed broker cancellation and performs a second
reconciliation that must return clean.
"""
from __future__ import annotations
import argparse,json,os,time,sys
from decimal import Decimal
from pathlib import Path
if os.environ.get("EXECUTION_ENV","demo").strip().lower()!="demo": raise SystemExit("EXECUTION_ENV must be demo")
REPO_ROOT=Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path: sys.path.insert(0,str(REPO_ROOT))
from apps.execution_gateway.mt5_gateway import DemoOnlyMT5Gateway
from apps.execution_gateway.mt5_orders import DemoOnlyMT5OrderAdapter
from apps.execution_gateway.runtime import DemoExecutionRuntime
from apps.trading_runtime.mt5_runtime import MT5RuntimeAdapter
from packages.models import AdmissionContext,EventState,Forecast,MarketState,PortfolioState,TradeIntent
from packages.demo_execution import SubmissionResult

def _build(rt,symbol):
    mt5r=MT5RuntimeAdapter(rt.gateway); now=int(time.time()*1000); q=mt5r.quote(symbol,now_ms=now); spec=mt5r.instrument_spec(symbol); acct=rt.gateway.account_snapshot()
    qty=spec.min_volume; dist=max(q.mid*Decimal("0.01"),spec.tick_size*10); limit=q.mid+dist*Decimal("2")
    intent=TradeIntent("evidence-drift-"+str(now),"demo-evidence","1","evidence",symbol,"SELL",qty,"LIMIT",limit,limit+dist,limit-dist*2,now,now+300000,Decimal("0.01"),Decimal("0.0001"),300,frozenset())
    ctx=AdmissionContext(now,q,Forecast("evidence","1",now,300,Decimal("0.01"),"fraction",Decimal("0.99"),Decimal("0.99"),Decimal("0.99")),MarketState(EventState.NORMAL,max(0,now-q.event_time_ms),q.spread/q.mid,Decimal("1"),Decimal("0"),Decimal("1"),Decimal("1")),PortfolioState(Decimal(str(acct["equity"])),Decimal("0"),Decimal("0"),Decimal("0"),0,Decimal("0"),Decimal("0"),False),Decimal("0.0001"),Decimal("0"))
    return intent,ctx,spec

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--symbol",default=os.environ.get("AG_SYMBOLS","USDJPY").split(",")[0]); ap.add_argument("--output",default="artifacts/evidence/demo-reconciliation-drift.json"); a=ap.parse_args()
    gw=DemoOnlyMT5Gateway(); gw.connect_and_verify_demo(); rt=None
    try:
        rt=DemoExecutionRuntime.create(); intent,ctx,spec=_build(rt,a.symbol)
        attempt=rt.submit(intent=intent,context=ctx,instrument=spec)
        if attempt.decision!="SUBMITTED" or not attempt.broker_order_id: raise RuntimeError(f"order placement failed:{attempt.decision}")
        mt5=gw.mt5_api()
        cancel=mt5.order_send({"action":getattr(mt5,"TRADE_ACTION_REMOVE"),"order":int(attempt.broker_order_id)})
        if cancel is None or int(getattr(cancel,"retcode",-1))!=int(getattr(mt5,"TRADE_RETCODE_DONE",-2)): raise RuntimeError("out-of-band broker cancellation failed")
        drift=rt.reconciliation.reconcile_once()
        frozen=drift.freeze_required and not rt.reconciliation.trading_permitted
        if not frozen: raise RuntimeError(f"reconciliation failed to freeze on drift:{drift.status}")
        rt.orders.mark_cancel_requested(attempt.order_id)
        rt.orders.record_cancellation(attempt.order_id,SubmissionResult("ACCEPTED",broker_order_id=attempt.broker_order_id,reason="DRILL_EXTERNAL_CANCEL_CONFIRMED_BY_RECONCILIATION"))
        clean=rt.reconciliation.reconcile_once()
        recovered=clean.status=="MATCHED" and not clean.freeze_required and rt.reconciliation.trading_permitted
        if not recovered: raise RuntimeError(f"reconciliation did not recover after explicit durable resolution:{clean.status}")
        report={"status":"PASS","order_id":attempt.order_id,"broker_order_id":attempt.broker_order_id,"drift_status":drift.status,"drift_freeze":frozen,"recovery_status":clean.status,"recovered":recovered}
        Path(a.output).parent.mkdir(parents=True,exist_ok=True); Path(a.output).write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8"); print(json.dumps(report,sort_keys=True)); return 0
    finally:
        if rt: rt.close()
        gw.shutdown()
if __name__=="__main__": raise SystemExit(main())
