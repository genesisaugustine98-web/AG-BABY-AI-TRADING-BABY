# Institutional FX Edge — Trading OS v2

**Author: Genesis Koodanga Augustine — September 2026**

This repository is the engineering control plane for an evidence-first FX research, decision, risk and **demo-only** execution system.

## Current architecture

`data -> quality -> provenance -> evidence -> forecast/ensemble -> opportunity -> deterministic risk -> durable order -> broker -> confirmed deal ingestion -> atomic accounting -> reconciliation -> TCA -> cockpit`

The design deliberately does **not** make an LLM the trader. The protected execution boundary is:

`AI/research proposal -> quantitative validation -> risk engine -> hard limits -> execution engine -> broker`

Live trading is disabled. MT5 submission is demo-only and the kernel itself accepts only `demo` or `paper` environments.

## Implemented foundations

- Point-in-time market-data contracts with `event_time` / `usable_at` boundaries.
- Fixed research splits, explicit costs/delay, evidence records and negative knowledge.
- Multiple-testing and probability-calibration primitives.
- Pluggable provider/model contracts with provenance-preserving ensemble forecasts.
- Deterministic executable-edge opportunity candidates.
- Deterministic portfolio/order risk gates with explicit health, drawdown, loss and position limits.
- Durable internal-order repository with environment-scoped identity.
- Demo-only MT5 order validation, `order_check`, `order_send`, bounded UNKNOWN recovery, cancel, pending replace and explicit expiry controls.
- Actual MT5 deal-history ingestion with explicit internal-order binding and restart-safe watermarks.
- Atomic broker-confirmed fill accounting in Supabase, including immutable fills, positions, audit events and execution TCA.
- Broker reconciliation with persistent freeze/unfreeze control state.
- Broker account snapshots and an authenticated, read-only Next.js operations cockpit.
- Deterministic demo/paper parity checks, fault/soak harnesses, persistent model surveillance/retirement and centralized runtime alerts.
- Restart-aware MT5 broker-order event stream facade and fail-closed cross-currency portfolio valuation.
- CI covering Python safety tests plus Next.js lint/build.

## Repository structure

- `packages/` — deterministic domain, research, risk, execution and intelligence primitives.
- `apps/execution_gateway/` — MT5 gateway, deal ingestion and demo order adapter.
- `apps/reconciliation/` — restart-safe broker reconciliation and confirmed-deal runtime.
- `apps/research/` — PIT data, replay, evidence and fixed-grid experiments.
- `integrations/` — Supabase persistence, platform health and control-plane adapters.
- `app/`, `components/`, `lib/` — authenticated read-only operator cockpit.
- `supabase/migrations/` — database source of truth for execution/control-plane schema.
- `tests/` — deterministic safety and regression suite.
- `docs/` — execution, provenance, evidence, integration and runtime specifications.

## Demo runtime

The intended trusted-server sequence is:

1. Set `EXECUTION_ENV=demo`.
2. Configure `SUPABASE_URL` and a server-side Supabase service key.
3. Configure `MT5_SERVER`, `MT5_DEMO_SERVER`, `MT5_LOGIN`, `MT5_PASSWORD` and optional terminal path.
4. Start the reconciliation worker first; it bootstraps broker truth and keeps execution frozen until a clean reconciliation exists.
5. Submit intents only through `ExecutionKernel` after policy/risk admission.
6. Treat `ACCEPTED` as acknowledgement, never as a fill. Actual fills enter through MT5 deal ingestion.

## Cockpit

The Next.js cockpit is read-only by design. Set `COCKPIT_ACCESS_TOKEN` server-side. The browser never receives the Supabase service key or broker credentials.

## Database

The connected Supabase project is protected with RLS and service-role-only execution/control tables. The execution ledger is append-only at the event level, with atomic confirmed-fill accounting and environment-scoped state.

## Research doctrine

A strategy is not promoted because it looks good in-sample. Require point-in-time data, out-of-sample evaluation, realistic costs/delay, calibration, regime/stress analysis, multiple-testing controls, explicit retirement criteria, and durable research lineage.

## Integration doctrine

GitHub remains the source of truth. External platforms consume versioned artifacts through adapters, APIs or CI jobs. Credentials remain outside source control, and execution environments are explicitly bounded.

## Status boundary

This release is a substantially integrated **research + execution-control foundation**, not a claim of trading profitability or a fully autonomous production trading desk. Production-quality live trading requires a separate reviewed authorization and additional operational controls beyond the demo boundary.

## Build baseline

Historical baseline: on the 2026-09-17 synchronized snapshot, 165 Python tests passed and the Next.js lint/production build passed. The current hardening branch has added substantial additional safety/regression coverage, so current CI results—not the historical count—are the release gate. Vercel deployment remains an external deployment-system check.


## Canonical autonomous runtime

The repository now exposes one composition root for the demo execution body system:

~~~bash
python -m apps.trading_runtime
~~~

That process binds MT5 market data, per-symbol TSMOM models, evidence-gated model governance, correlation-aware portfolio allocation, deterministic policy/risk, durable order identity, broker reconciliation, tamper-evident runtime events, fenced multi-host ownership, execution circuit breakers, localhost health/Prometheus telemetry, lifecycle supervision, host singleton control, and fail-safe shutdown. Execution remains explicitly demo-only; credentials stay in server-side environment variables. Deployment details are in `docs/CANONICAL_RUNTIME.md`, and the institutional operating contract is in `docs/INSTITUTIONAL_RUNTIME.md`.


## New operator controls

Set AG_ALERTS_ENABLED=true to persist critical runtime safety alerts; optionally set AG_ALERT_WEBHOOK_URL=https://... for secondary HTTPS fan-out. The database remains the authoritative alert sink.

For non-USD instruments, configure AG_PORTFOLIO_FX_SYMBOLS with the broker symbols that provide current USD conversion paths. Missing conversion data is rejected rather than estimated.

The event-stream facade is available from the demo runtime through poll_broker_events(). It is restart-aware and can use the existing Supabase ingestion checkpoint, but the MT5 Python API underneath remains polling-based.

Model surveillance is available through ModelSurveillanceService; consecutive breaches are persisted and a retired model is not automatically reactivated.

All of these additions remain below the same hard boundary: live capital execution is disabled.
