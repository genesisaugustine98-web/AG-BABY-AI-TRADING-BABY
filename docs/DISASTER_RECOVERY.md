# Disaster Recovery Runbook

## Primary invariant

After a process, host, database or network failure, the broker is the source of truth. The runtime must reconcile before submitting anything.

## Process crash

1. Durable execution state remains in Supabase.
2. The Windows supervisor may restart the process.
3. Startup obtains the local lock and, when configured, the fenced distributed lease.
4. MT5 is reconnected and positively verified as demo.
5. Broker orders and positions are reconciled.
6. Nonterminal durable orders rebuild risk reservations.
7. Unresolved drift freezes the runtime.

## Host replacement

Provision a clean Windows execution host. Do not copy broker credentials through source control.

Install the pinned runtime dependencies, configure server-side secrets, install the matching MT5 terminal, deploy the exact release commit and perform reconciliation before enabling autonomous demo submission.

## Database outage

The system must not infer durable truth while Supabase is unavailable. Keep execution frozen. After the database recovers, verify control state, event integrity and order state before resuming.

## Broker outage

Keep autonomous submission frozen until the terminal is connected and broker state is freshly reconciled.

## Back-to-back failures

A restart after an earlier UNKNOWN state must not submit a new order with the same logical intent until the old client-order identity has been resolved against broker truth.

## Recovery acceptance criteria

A recovered node is not accepted merely because the process is running. It must have:

- a valid demo broker connection
- clean reconciliation
- valid account/position snapshots
- no unexplained active order
- no unexplained position drift
- intact runtime audit verification for the recovered window
- valid model/code/data identity
- active runtime ownership lease when multi-host mode is enabled
- healthy heartbeat

## Evidence retention

Preserve broker order/deal history, durable execution events, reconciliation records, account snapshots, risk decisions, model registry lineage, deployment commit SHA, and incident/change records.

Recovery evidence must be sufficient for an independent reviewer to reconstruct what the robot believed, what the broker actually reported, and why each order was or was not allowed.
