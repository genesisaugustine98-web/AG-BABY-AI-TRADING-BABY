# Runtime Operations

## Runtime contract

The trading node is a long-running orchestration shell. It does not replace the deterministic
execution kernel. Its job is to schedule strategy evaluations, publish typed events, monitor
runtime health and invoke execution only when explicitly enabled.

## Safe startup

1. Start the trusted execution/reconciliation runtime first.
2. Require a fresh clean broker reconciliation before permitting trading.
3. Hydrate authoritative account and position state.
4. Start the TradingNode.
5. Keep allow_execution=false during research, connectivity and smoke-test sessions.
6. When demo execution is intentionally enabled, provide a demo execution sink; the underlying
   kernel and MT5 gateway still enforce their own environment checks.

## Health rules

- An unmeasured liquidity, broker-health or data-health value is zero and therefore blocks the
  candidate at the opportunity/policy layer.
- A broker quote whose event timestamp is in the future freezes the runtime.
- A stale heartbeat is non-operational.
- An unexpected cycle exception freezes the node and emits a FreezeEvent.
- Reconciliation is an independent source of truth and can keep the execution gateway frozen.

## Recovery rules

UNKNOWN is not a retry instruction. Resolve it from broker truth first. Reconciliation drift,
ambiguous order identity, duplicate broker identity, missing broker truth, or unresolved fills
must leave the system frozen until explicitly reconciled.

## Observability

The runtime emits MarketQuoteEvent, ForecastEvent, OpportunityEvent, OrderLifecycleEvent,
HeartbeatEvent and FreezeEvent records. RuntimeMetrics tracks cycle failures, candidate admission,
execution UNKNOWN/rejection counts, freezes, observer failures and cycle latency.

The Next.js cockpit remains read-only. Credentials remain server-side.

## Deployment

A deployment should pin an immutable repository commit, use platform-native secret storage,
perform startup reconciliation, report heartbeats, expose health state, and support graceful
stop/restart. Live execution remains disabled by repository design.
