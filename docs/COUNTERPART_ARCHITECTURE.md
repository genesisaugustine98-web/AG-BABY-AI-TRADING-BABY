# Counterpart-Level Runtime Architecture

The repository now contains a runtime shell around the research, risk, execution and
reconciliation foundation. The design takes architectural lessons from established
event-driven trading engines without introducing a third-party trading framework.

## Component map

| Layer | AG-BABY implementation | Purpose |
|---|---|---|
| Runtime node | apps/trading_runtime/node.py | Lifecycle, scheduling, orchestration and heartbeats |
| Event model | packages/events.py | Immutable typed runtime events |
| Event bus | packages/event_bus.py | Ordered routing with critical/non-critical handlers |
| Supervision | packages/runtime_supervisor.py | Start/run/freeze/fail/stop state machine |
| Portfolio | packages/portfolio_engine.py | Broker-authoritative account and position aggregation |
| Strategy controllers | packages/strategy_controller.py | Strategy-specific forecast/candidate generation |
| Execution kernel | packages/execution_kernel.py | Durable intent, risk/policy, submit-once, UNKNOWN handling |
| Reconciliation | apps/reconciliation | Broker truth, confirmed deals and freeze/unfreeze |
| MT5 runtime adapter | apps/trading_runtime/mt5_runtime.py | Quotes, contract metadata and completed bars |
| Cockpit | app + lib | Authenticated read-only operational visibility |

## Invariants

1. Strategy controllers produce candidates, never broker orders.
2. Candidates cannot bypass policy, risk or the durable execution kernel.
3. Runtime execution is opt-in and must use an explicit execution sink.
4. The current broker path remains demo/paper bounded.
5. UNKNOWN broker submissions are resolved from broker truth and never blindly retried.
6. Portfolio readiness requires authoritative account/position data.
7. Non-critical observer failures are recorded; critical handler failures surface.
8. Runtime health requires a fresh heartbeat.
9. Reconciliation remains independent and can freeze execution.
10. Credentials never enter runtime events or strategy evidence.

## Counterpart-derived additions

The architecture now has explicit seams for the major concepts seen in mature systems:

- long-running node/controller lifecycle;
- typed event flow between data, strategy, risk, execution and reconciliation;
- broker contract discovery at runtime;
- portfolio state aggregation and risk reservations;
- synchronous deterministic orchestration suitable for replay and tests;
- runtime heartbeat and freeze/fail state transitions.

The next maturity increments are operational rather than architectural rewrites:
streaming broker/user events where available, durable event sourcing and replay, richer
portfolio factor/correlation models, complete cancel/replace/expiry lifecycle operations,
model promotion/retirement state machines, metrics/traces/alerts, multi-process watchdogs,
and deployment-grade configuration/version manifests.

## Boundary

This release intentionally does not enable live execution. The MT5 gateway positively proves
demo mode, the execution kernel accepts only demo/paper, and the research slate keeps live
promotion disabled.
