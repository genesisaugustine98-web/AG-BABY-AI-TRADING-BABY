# Institutional Runtime Contract

This document defines what the current AG-BABY runtime guarantees, what it deliberately refuses to do, and what must be proven before any future capital-authorized environment is considered.

## 1. Safety boundary

The canonical autonomous runtime is permanently demo-only in this repository.

A valid startup requires:

1. EXECUTION_ENV=demo.
2. A positively verified MT5 demo account/server.
3. A fresh clean broker reconciliation.
4. Authoritative broker account and position state.
5. Valid point-in-time strategy data.
6. Model-governance evidence when execution is enabled.
7. Deterministic candidate allocation.
8. Correlation-aware portfolio-risk admission.
9. Deterministic policy and order-risk approval.
10. Durable internal-order creation before broker submission.
11. Fresh broker reconciliation immediately before every broker submission.
12. A healthy runtime heartbeat.
13. A current distributed lease when AG_DISTRIBUTED_LEASE=true.
14. A successful durable audit event write; the canonical runtime attaches the event store as critical.
15. A broker-safe execution outcome. UNKNOWN is never interpreted as a clean rejection.

A failure in a protected boundary must either deny the action or freeze the runtime.

## 2. Multi-host ownership

The host-local SingletonLock prevents duplicate execution processes on one machine.

For multi-host deployments, enable the Postgres-backed fenced lease:

    AG_DISTRIBUTED_LEASE=true
    AG_LEASE_NAME=ag-demo-execution
    AG_LEASE_TTL_SECONDS=30

The lease uses an owner identity plus a monotonic fencing token in Postgres. A node that loses its token cannot renew and is forced into the frozen state.

Only the trusted server should have the Supabase secret key required to call the lease RPCs.

## 3. Portfolio admission

The strategy allocator is now correlation-aware at the risk-budget boundary.

For multiple symbols, declare known correlations:

    AG_REQUIRE_COMPLETE_CORRELATIONS=true
    AG_PORTFOLIO_CORRELATIONS={"EURUSD,GBPUSD":"0.78","EURUSD,USDJPY":"-0.20","GBPUSD,USDJPY":"-0.10"}

Unknown correlations are rejected when complete-correlation mode is enabled. When that requirement is deliberately disabled, a conservative correlation floor is used rather than silently assuming zero correlation.

The allocator also accounts for currently reserved order risk, strategy concentration, instrument concentration, candidate count, total risk and signed directional risk.

## 4. Runtime circuit breaker

The default execution circuit breaker trips on the first broker UNKNOWN outcome.

That is intentional. An ambiguous submission means the broker may have accepted the order even if the client did not receive the acknowledgement. The correct response is truth acquisition and freeze/recovery, not automatic resubmission.

Repeated ordinary broker rejections also trip the circuit after the configured threshold.

    AG_MAX_EXECUTION_UNKNOWN=1
    AG_MAX_EXECUTION_REJECTIONS=5

## 5. Tamper-evident runtime audit

Runtime events are durably persisted with:

- event identity
- event type
- correlation identity
- provenance
- serialized payload
- previous event hash
- current event hash

The runtime event store computes a SHA-256 chain and exposes deterministic verification for forensic replay.

The event bus attaches this audit sink as critical in the canonical autonomous runtime. A persistence failure therefore blocks continued autonomous operation instead of silently losing audit records.

## 6. Health and observability

Optional loopback-only endpoints are available:

    AG_METRICS_ENABLED=true
    AG_METRICS_HOST=127.0.0.1
    AG_METRICS_PORT=9300

Endpoints:

- /healthz — process health and counters.
- /readyz — runtime-ready signal.
- /metrics — Prometheus-compatible scalar metrics.

The service is loopback-only to avoid exposing operational state directly to the network. The authenticated cockpit remains the human-facing control-plane view.

## 7. Data integrity

The canonical market-state layer rejects:

- non-positive bid/ask prices
- crossed markets
- missing quote source provenance
- future-dated quotes
- negative quote age

Spread stress and stale-data conditions reduce executable health and can prevent policy/risk admission.

## 8. Restart semantics

A restart never assumes local state is authoritative.

Startup flow:

    process starts
       ->
    obtain host lock
       ->
    optional obtain distributed lease
       ->
    connect and positively verify MT5 demo
       ->
    hydrate persistent freeze state
       ->
    reconcile broker orders/positions
       ->
    refresh authoritative account state
       ->
    rebuild nonterminal order-risk reservations
       ->
    rebuild strategy risk from a fresh local accumulator
       ->
    fit/validate model
       ->
    governance gate
       ->
    runtime ready

A restart that cannot establish broker truth remains non-tradable.

## 9. Failure matrix

### MT5 terminal crashes

The node must not infer broker state from the client process. Reconnect/reconciliation is required before execution resumes.

### Network disappears

The runtime fails closed. It does not manufacture broker acknowledgements or fills.

### Submission returns UNKNOWN

The circuit breaker freezes. No blind retry is permitted.

### Supabase becomes unavailable

Critical runtime-event persistence or durable execution-control operations fail closed.

### Quote becomes future-dated or crossed

The cycle fails rather than feeding malformed state into the strategy.

### Two hosts attempt execution

The distributed fenced lease allows only the valid owner token to renew.

### Process dies after writing an order but before receiving an acknowledgement

The durable order identity remains in the ledger and the next startup reconciles against broker truth before any new submission.

### A human wants to resume after a freeze

The human cannot bypass reconciliation by editing process memory. The durable state must be cleared only through a controlled workflow, and the broker must reconcile cleanly first.

## 10. Deployment topology

Preferred production-like demo topology:

    source / CI
          |
    versioned release
          |
    +-----+----------------------+
    |                            |
    v                            v
    Linux control/research       Windows execution host
                                 |                 |
                                 |                 +-- local singleton
                                 |                 +-- optional fenced lease
                                 |                 +-- Python runtime
                                 |                 +-- MT5 terminal
                                 |                 +-- loopback metrics
                                 |
                                 +--------- secure link ---------+
                                                                  |
                                                                  v
                                                             Supabase
                                                        durable control/audit

The Windows execution host should be treated as a dedicated financial appliance rather than a general-purpose workstation.

## 11. Promotion doctrine

The repository does not claim that the trading strategy is profitable.

Before any capital authorization, require:

- multi-period walk-forward evidence
- untouched holdout evidence
- realistic bid/ask and slippage assumptions
- financing/swap costs
- transaction-cost stress
- parameter perturbation
- multiple-testing control
- regime analysis
- model drift monitoring
- broker execution statistics
- prolonged demo soak
- fault-injection results
- reconciliation-drift history
- zero unexplained order/position mismatches

Demo success is an engineering signal, not proof of economic edge.

## 12. Current maturity boundary

The current system is a credible autonomous demo execution platform with strong control-plane foundations.

It is not yet a fully operational institutional trading desk because the following still require evidence or further integration:

- streaming broker/user-event infrastructure beyond polling
- complete integration of raw portfolio notionals with the allocation risk layer
- persisted model promotion/retirement workflow across the entire lifecycle
- full cancel/replace/expire execution adapters
- external alert routing and tracing
- long-duration soak results
- independent disaster-recovery exercises
- strategy profitability evidence across sufficiently independent samples
- formal change-management and capital-authorization process

These are explicit boundaries, not hidden assumptions.
