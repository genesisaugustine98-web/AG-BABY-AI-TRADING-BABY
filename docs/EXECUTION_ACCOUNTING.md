# Execution accounting and TCA boundary

## Source-of-truth hierarchy

1. Broker-confirmed fill data is the only source allowed to create an execution fill.
2. `execution_fills` is immutable execution evidence and is keyed by `fill_id`; broker fill identity is also constrained by `(order_id, broker_fill_id)` when supplied.
3. `execution_positions` is a deterministic projection of persisted confirmed fills. It is rebuildable and is not treated as independent account truth.
4. Broker positions and broker order state remain authoritative external truth during reconciliation.
5. A theoretical order acknowledgement is never converted into a fill.

## MT5 deal boundary

MT5's Python `history_deals_get(date_from, date_to, ...)` returns historical deals for a bounded interval and may also filter by order or position. MQL5 defines a deal as the execution of a trade operation, with unique deal ticket, order ticket, execution time, deal type, entry direction, volume, price, commission, swap, profit, and fee fields. The collector therefore reads `DEAL_TYPE_BUY` and `DEAL_TYPE_SELL` records only and rejects malformed trade records. Non-trading history entries are ignored rather than converted into fills. citeturn233757search0turn233757search2

`apps/execution_gateway/mt5_fills.py` keeps broker deal identity separate from internal order identity. A normalized `BrokerDealRecord` can only become a canonical `BrokerConfirmedFill` after an explicit `bind_internal_order(internal_order_id)` step. This prevents a broker ticket, comment, or acknowledgement from being silently treated as an internal intent mapping.

Deal entry semantics (`IN`, `OUT`, `INOUT`/reverse, and `OUT_BY`) are preserved in metadata rather than discarded. Execution timestamp prefers `time_msc` and falls back to `time`; the broker ticket remains the immutable fill identity. These fields are useful for audit and downstream position/reconciliation logic. citeturn233757search2

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

Supabase's current security model for public-schema Data API access requires explicit exposure/grants in addition to RLS for newly controlled tables; this bridge therefore remains server-side and must not expose the secret key to browser clients. citeturn624003search9turn125file0

The position write is intentionally treated as a projection update rather than an atomic account transaction. If a process crashes after the fill insert and before the projection update, the fill remains durable and the projection can be deterministically rebuilt. Claiming atomic fill-plus-position semantics would require a database transaction/RPC or direct Postgres transaction boundary that is not yet implemented here.

## Legacy database state

The current project contains one older demo accounting row (`acct-test-fill-1`) whose execution event says `BROKER_CONFIRMED_FILL`, while its corresponding order row reports zero filled quantity. That pair is retained as historical test data and is not treated by the new canonical bridge as a valid projection input because its metadata lacks the canonical `source_truth` and instrument markers. It should not be used as evidence of market execution.

## What remains outside this layer

A production broker adapter still has to collect broker deal/fill records independently from order acknowledgements, reconcile those fills against internal order identities, and feed the confirmed fill stream into this accounting boundary. Live/demo execution, broker-specific deal semantics, account-currency conversion, market-data markout collection, and independent risk authorization remain separate gates.
