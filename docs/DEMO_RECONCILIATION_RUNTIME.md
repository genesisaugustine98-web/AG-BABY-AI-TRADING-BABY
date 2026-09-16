# Demo reconciliation runtime

This runtime is reconciliation-only. It does not place orders.

## Required server environment

```text
EXECUTION_ENV=demo
MT5_SERVER=<exact demo server name>
MT5_DEMO_SERVER=<same allowlisted demo server name>
MT5_LOGIN=<demo login>
MT5_PASSWORD=<demo password>
MT5_TERMINAL_PATH=<optional terminal path>
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<server-only secret>
RECONCILIATION_INTERVAL_SECONDS=15
```

`SUPABASE_SERVICE_ROLE_KEY` must never be placed in frontend code, browser variables, public configuration, or committed files.

## Runtime invariant

Startup never means trading-ready. `DurableReconciliationService.startup()` hydrates persisted control state and leaves the process non-tradable until a fresh broker snapshot is reconciled.

A clean reconciliation produces `READY`. Drift or broker failure produces a freeze. The service never interprets an acknowledgement as a fill and never invents broker identity when a client order ID is missing.

## MT5 demo proof

The connector refuses non-demo execution environments, requires the broker server to match the explicit demo allowlist, requires credentials, and requires a positive demo-account trade-mode check before remaining connected.

## Current limitation

This entrypoint is intentionally not an order-placement daemon. Before any autonomous order placement is enabled, the system still needs a separately reviewed, idempotent order-submission adapter plus a broker-confirmed order/fill lifecycle and an independent risk kill path.
