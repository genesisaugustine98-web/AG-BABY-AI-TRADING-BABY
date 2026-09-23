"""Two-phase real HFM-demo UNKNOWN recovery drill.

Phase submit places a far-away pending order, deliberately discards the broker
acknowledgement after order_send, and exits. Phase recover starts a fresh Python
process, resolves the durable UNKNOWN against broker truth, and cancels the demo
order. No live-capital path is reachable.
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

class AmbiguousBroker:
    def __init__(self,adapter): self.adapter=adapter
    def submit(self,request): self.adapter.submit(request); raise RuntimeError("INJECTED_PROCESS_CRASH_AFTER_ORDER_SEND")

def _build(runtime, symbol):
    mt5r=MT5RuntimeAdapter(runtime.gateway); now=int(time.time()*1000); q=mt5r.quote(symbol,now_ms=now); spec=mt5r.instrument_spec(symbol); acct=runtime.gateway.account_snapshot()
    qty=spec.min_volume; dist=max(q.mid*Decimal("0.01"),spec.tick_size*10); limit=q.mid-dist*Decimal("2")
    intent=TradeIntent("evidence-recovery-"+str(now),"demo-evidence","1","evidence",symbol,"BUY",qty,"LIMIT",limit,limit-dist,limit+dist*2,now,now+300000,Decimal("0.01"),Decimal("0.0001"),300,frozenset())
    ctx=AdmissionContext(now,q,Forecast("evidence","1",now,300,Decimal("0.01"),"fraction",Decimal("0.99"),Decimal("0.99"),Decimal("0.99")),MarketState(EventState.NORMAL,max(0,now-q.event_time_ms),q.spread/q.mid,Decimal("1"),Decimal("0"),Decimal("1"),Decimal("1")),PortfolioState(Decimal(str(acct["equity"])),Decimal("0"),Decimal("0"),Decimal("0"),0,Decimal("0"),Decimal("0"),False),Decimal("0.0001"),Decimal("0"))
    return intent,ctx,spec

def submit(symbol,handoff):
    rt=DemoExecutionRuntime.create()
    try:
        intent,ctx,spec=_build(rt,symbol)
        attempt=rt.kernel.execute(intent=intent,context=ctx,instrument=spec,repository=rt.orders,broker=AmbiguousBroker(DemoOnlyMT5OrderAdapter(rt.gateway.mt5_api())))
        payload={"order_id":attempt.order_id,"client_order_id":attempt.client_order_id,"decision":attempt.decision,"created_at":time.time()}
        if attempt.decision!="UNKNOWN" or not attempt.order_id: raise RuntimeError(f"ambiguity drill did not produce UNKNOWN:{attempt.decision}")
        Path(handoff).parent.mkdir(parents=True,exist_ok=True); Path(handoff).write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8"); print(json.dumps(payload,sort_keys=True)); return 0
    finally: rt.close()

def recover(handoff):
    payload=json.loads(Path(handoff).read_text(encoding="utf-8"))
    rt=DemoExecutionRuntime.create()
    try:
        recovered=rt.recover(order_id=payload["order_id"],client_order_id=payload["client_order_id"])
        if recovered.outcome!="ACCEPTED" or not recovered.broker_order_id: raise RuntimeError(f"broker truth did not resolve UNKNOWN:{recovered.outcome}")
        cleanup=rt.cancel_order(order_id=payload["order_id"])
        if not cleanup.allowed: raise RuntimeError("demo order cleanup was not confirmed")
        result={"status":"PASS","client_order_id":payload["client_order_id"],"broker_order_id":recovered.broker_order_id,"recovery":"ACCEPTED","cleanup":None if cleanup.result is None else cleanup.result.outcome}
        Path(handoff).write_text(json.dumps({**payload,**result},indent=2)+"\n",encoding="utf-8"); print(json.dumps(result,sort_keys=True)); return 0
    finally: rt.close()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--phase",choices=("submit","recover"),required=True); ap.add_argument("--symbol",default=os.environ.get("AG_SYMBOLS","USDJPY").split(",")[0]); ap.add_argument("--handoff",default="artifacts/evidence/demo-unknown-recovery.json")
    a=ap.parse_args(); return submit(a.symbol,a.handoff) if a.phase=="submit" else recover(a.handoff)
if __name__=="__main__": raise SystemExit(main())
