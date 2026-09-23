# Demo Evidence Runbook

This runbook turns the remaining evidence requirements into repeatable operator exercises. It deliberately separates three kinds of evidence:

- **Historical**: deterministic strategy validation over completed broker data with fixed chronological splits and explicit cost assumptions.
- **Simulated**: controlled fault-injection tests of runtime invariants. These prove software behavior, not infrastructure availability.
- **Live demo**: observations made against the verified HFM demo account and persisted in the evidence artifact.

## 1. Prerequisites

Use a dedicated Windows host with the HFM MT5 terminal installed and already logged into the intended demo account. The repository must be checked out at the exact commit under test.

Provide these values as machine/environment secrets; never commit them:

```
EXECUTION_ENV=demo
MT5_LOGIN=...
MT5_PASSWORD=...
MT5_SERVER=...
MT5_DEMO_SERVER=...
MT5_TERMINAL_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
SUPABASE_URL=https://...
SUPABASE_SECRET_KEY=...
AG_SYMBOLS=USDJPY
```

For GitHub-hosted execution, use a dedicated self-hosted runner with labels `self-hosted,Windows,mt5-demo`. Put the broker/database credentials in the protected GitHub environment used by the workflow.

## 2. Software evidence

Run:

```
python scripts/run_evidence_pack.py --output artifacts/evidence/simulated-evidence.json
```

Expected result: all simulated control-plane drills are `PASS`; live-demo evidence remains `UNOBSERVED`. That is intentional.

## 3. Real UNKNOWN / restart recovery drill

This is the most important process-boundary execution test.

First process:

```
python scripts/run_demo_submit_recovery.py --phase submit --symbol USDJPY --handoff artifacts/evidence/unknown-handoff.json
```

The process intentionally discards the broker acknowledgement after `order_send`, persists the order as `UNKNOWN`, and exits.

Second process:

```
python scripts/run_demo_submit_recovery.py --phase recover --handoff artifacts/evidence/unknown-handoff.json
```

The new process must reconnect, reconcile, resolve the client-order identity from broker truth, and cancel the pending demo order.

Acceptance:
- initial phase = `UNKNOWN`
- recovery = `ACCEPTED`
- broker ticket discovered after restart
- cleanup cancellation confirmed
- no duplicate submission occurred

## 4. Real reconciliation-drift drill

Run:

```
python scripts/run_demo_reconciliation_drift.py --symbol USDJPY --output artifacts/evidence/reconciliation-drift.json
```

The drill places a far-away pending demo order, cancels it outside the durable order-control layer, and forces reconciliation to observe the mismatch.

Acceptance:
- broker/internal mismatch is detected
- durable execution freeze becomes active
- ordinary trading permission is false while drift exists
- explicit durable resolution is required
- a second reconciliation returns `MATCHED`
- trading permission becomes true only after the clean reconciliation

## 5. Prolonged demo soak

For the actual 24-hour observation:

```
python scripts/run_demo_evidence.py --duration-minutes 1440 --interval-seconds 15 --symbols USDJPY --output artifacts/evidence/demo-evidence.json
```

The collector repeatedly records:
- broker account truth
- broker order/position snapshot
- reconciliation status
- restart-aware order-event ingestion
- account snapshots in Supabase

A 24-hour evidence record is only marked `PASS` when the requested duration completed and no collection/reconciliation error occurred.

## 6. Strategy validation

The demo evidence collector also executes the fixed TSMOM H1 validation on the configured symbols using:
- development / validation / holdout chronological separation
- fixed 24-bar lookback
- fixed 6-bar horizon
- 1-bar execution delay
- explicit 0/1/2/5/10 bps one-way cost sensitivity

The report is descriptive only. It does not promote a model or establish profitability.

For execution-grade historical bid/ask evaluation, additionally run:

```
python scripts/run_tsmom_hfm_tick_economic_validation.py --symbol USDJPY --count 5000 --delay-bars 1
```

## 7. Network and database outage exercises

The repository has deterministic failure drills for reconciliation/database faults. Those are **SIMULATED** evidence unless the operator records an actual infrastructure outage.

For a real outage exercise, use an isolated demo window and intentionally interrupt the relevant connectivity for the shortest controlled interval, then verify:
- no new submission occurs during the outage
- runtime becomes or remains frozen
- no fake broker/account truth is synthesized
- recovery requires restored connectivity plus clean reconciliation
- the evidence artifact contains timestamps, failure window and recovery reconciliation

Do not improvise an outage against production infrastructure.

## 8. Evidence interpretation

A complete evidence pack should contain:
- exact commit SHA
- dataset fingerprints
- historical strategy metrics
- real demo soak duration/cycles
- reconciliation results
- order-event checkpoint state
- UNKNOWN recovery report
- reconciliation-drift report
- fault-injection report
- model/code/data identities

The gate is deliberately fail-closed. `UNOBSERVED` is not a pass.

Live capital execution remains disabled throughout these exercises.
