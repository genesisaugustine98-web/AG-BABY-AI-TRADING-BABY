# Institutional Readiness Checklist

This checklist separates software correctness from economic evidence. A green software build never means that the trading strategy is profitable.

## Gate 0 — Source integrity

- [ ] Exact commit SHA recorded.
- [ ] Dependency audit passes.
- [ ] Windows deployment scripts parse successfully.
- [ ] No broker/database secret is present in source control.
- [ ] Release manifest and configuration fingerprint recorded.

## Gate 1 — Runtime correctness

- [ ] Full Python test suite passes.
- [ ] Python compilation passes.
- [ ] Dependency consistency check passes.
- [ ] Web lint and production build pass.
- [ ] Integration-health passes.
- [ ] Canonical runtime rejects non-demo environment.

## Gate 2 — Broker truth

- [ ] MT5 terminal is verified as demo.
- [ ] Account snapshot is current.
- [ ] Position snapshot is current.
- [ ] Order reconciliation is clean.
- [ ] Fresh reconciliation is required before every submission.
- [ ] UNKNOWN execution is frozen and reconciled rather than retried blindly.

## Gate 3 — Portfolio safety

- [ ] Order-level risk gate passes.
- [ ] Coarse strategy/instrument/total allocator passes.
- [ ] Exact post-sizing portfolio gate passes.
- [ ] Gross notional limit passes.
- [ ] Net notional limit passes.
- [ ] Margin limit passes.
- [ ] Portfolio volatility limit passes.
- [ ] Beta limit passes when beta data is configured.
- [ ] Required pairwise correlations are available.
- [ ] No unsupported currency conversion is accepted.
- [ ] Required non-USD conversion symbols are configured when cross-currency exposures exist.

## Gate 4 — Ownership and audit

- [ ] Host-local singleton lock is held.
- [ ] Fenced distributed lease is enabled for multi-host deployments.
- [ ] Runtime event persistence is healthy.
- [ ] Runtime event hash chain verifies for the recovery window.
- [ ] Runtime instance ID is unique.
- [ ] Configuration fingerprint is stable for the run.
- [ ] Runtime safety alerts are durably persisted when alerting is enabled.
- [ ] Model surveillance state survives restart from durable observation history.
- [ ] Execution TCA is populated from confirmed fills when decision-mid telemetry exists.
- [ ] Model/dataset/feature/code lineage is persisted.

## Gate 5 — Reliability evidence

- [ ] 24-hour uninterrupted demo soak.
- [ ] Multi-day demo soak.
- [ ] Supervisor restart exercised.
- [ ] MT5 process crash exercised.
- [ ] Network outage exercised.
- [ ] Database outage exercised.
- [ ] Restart during order submission exercised.
- [ ] UNKNOWN order recovery exercised.
- [ ] Duplicate-instance test exercised.
- [ ] Clock rollback/jump exercised.
- [ ] Reconciliation drift test exercised.

## Gate 6 — Strategy evidence

- [ ] Development, validation and holdout periods are chronologically separated.
- [ ] Point-in-time data rules are enforced.
- [ ] Executable bid/ask costs are included.
- [ ] Slippage stress is included.
- [ ] Financing/swap costs are included.
- [ ] Parameter perturbation is included.
- [ ] Regime analysis is included.
- [ ] Multiple-testing / selection effects are addressed.
- [ ] Results survive genuinely untouched data.
- [ ] No profitability conclusion is based on one holdout period.

## Gate 7 — Capital authorization boundary

The current repository does not satisfy this gate because the canonical runtime is demo-only. Any future capital-enabled deployment must be a separately reviewed architecture and authorization boundary, not a one-line environment-variable change.

## What a green checklist means

A green engineering checklist means the machine behaved according to its specified controls under the tested conditions. It does not establish future returns, broker profitability, or absence of unforeseen market risk.
