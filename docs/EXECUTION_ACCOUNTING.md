# Execution accounting and TCA boundary

## Source-of-truth hierarchy

1. Broker-confirmed fill data is the only source allowed to create an execution fill.
2. `execution_fills` is immutable execution evidence and is keyed by `fill_id`; broker fill identity is also constrained by `(order_id, broker_fill_id)` when supplied.
3. `execution_positions` is a deterministic projection of persisted confirmed fills. It is rebuildable and is not treated as independent account truth.
4. Broker positions and broker order state remain authoritative external truth during reconciliation.
5. A theoretical order acknowledgement is never converted into a fill.

## Position projection

`packages/fill_accounting.py` uses exact `Decimal` arithmetic. Fills are replayed by `(filled_at, fill_id)` so arrival order does not change the resulting projection. Same-direction fills update weighted average price; opposing fills close existing inventory; a larger opposing fill closes the old side and opens the reversal remainder at the new fill price.

`realized_pnl` is quote-currency P&L under the convention that quantity is base quantity and price is quote-per-base. Conversion to account currency is intentionally outside this layer. Financing is tracked separately. Commission is preserved as execution data and may be signed to support rebates.

## Idempotency and conflict handling

A repeated `fill_id` with the same canonical fingerprint is a duplicate and is not applied twice. The same `fill_id` with different content is a hard conflict and must be investigated. A persistence race that violates the database uniqueness constraint is an error, not an excuse to invent a second fill.

## TCA

`packages/tca.py` computes:

- execution VWAP from confirmed fills;
- arrival mid and arrival spread from an independently observed reference quote;
- signed execution slippage in price units and basis points, where positive means adverse execution cost;
- post-trade markout, where positive means favorable subsequent market movement.

Without an independently observed arrival quote, TCA status is `UNKNOWN_ARRIVAL_QUOTE`. The system does not use the execution price itself as its own market benchmark.

## Durable Supabase adapter

`integrations/supabase_execution.py` is server-only. It uses `SUPABASE_SECRET_KEY` and never belongs in browser/client code. The adapter persists the fill fingerprint in metadata, reads the canonical persisted fill set, recomputes the position, and upserts the rebuildable position projection using one deterministic `(environment, instrument)` identity.

The position write is intentionally treated as a projection update rather than an atomic account transaction. If a process crashes after the fill insert and before the projection update, the fill remains durable and the projection can be deterministically rebuilt. Claiming atomic fill-plus-position semantics would require a database transaction/RPC or direct Postgres transaction boundary that is not yet implemented here.

## Legacy database state

The current project contains one older demo accounting row (`acct-test-fill-1`) whose execution event says `BROKER_CONFIRMED_FILL`, while its corresponding order row reports zero filled quantity. That pair is retained as historical test data and is not treated by the new canonical bridge as a valid projection input because its metadata lacks the canonical `source_truth` and instrument markers. It should not be used as evidence of market execution.

## What remains outside this layer

A production broker adapter still has to collect broker deal/fill records independently from order acknowledgements, reconcile those fills against internal order identities, and feed the confirmed fill stream into this accounting boundary. Live/demo execution, broker-specific deal semantics, account-currency conversion, market-data markout collection, and independent risk authorization remain separate gates.
