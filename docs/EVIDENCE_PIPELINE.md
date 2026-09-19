# Evidence Pipeline

The research pipeline is intentionally divided into data truth, causal availability, statistical summary, and promotion governance.

## 1. Data truth

Every observation carries event time, usable time, source, source version, observation ID, and execution-grade status. H.10 observations are reference data and remain `execution_grade=false`.

## 2. Causal availability

A release-time information set may contain only observations with `usable_at <= release_at` and `event_time <= release_at`. Future observations cause a hard failure.

## 3. Evidence statistics

Completed cells may report sample size, mean net return, median, population volatility, net win rate, compounded cumulative net return, maximum drawdown, and the analytical zero-mean breakeven one-way cost.

These are descriptive statistics. They are not proof of statistical significance, persistence, tradability, or capacity.

## 4. Research classification

The evidence gate requires predeclared minimum sample size and mean-net threshold and may require positive cumulative return. It does not permit holdout tuning. Classification is `supported`, `not_supported`, or `inconclusive` under the supplied research criteria.

## 5. Provenance gate

`revised_history` may be used for exploratory research and falsification, but it is not equivalent to a point-in-time vintage archive and cannot satisfy the point-in-time promotion gate.

## 6. Execution boundary

Nothing in this evidence pipeline authorizes live execution. Execution-grade market data, broker reconciliation, liquidity/TCA evidence, risk signoff, shadow/paper stages, and rollback controls remain separate promotion requirements.

## 7. Current limitation

The repository currently contains the acquisition and analysis machinery, but no verified multi-year point-in-time H.10 vintage dataset has been executed through this environment. Therefore this document must not be cited as evidence that any hypothesis has passed the empirical gate.


## 8. Execution-price-aware replay

For broker-integrated research, the repository now has a separate HFM/MT5 historical-quote adapter that reads COPY_TICKS_INFO Bid/Ask-change ticks and a TSMOM replay that prices hypothetical entries and exits from the executable side of the spread: BUY entries use Ask and exits use Bid; SELL entries use Bid and exits use Ask. MetaTrader 5 documents COPY_TICKS_INFO as the tick stream for Bid/Ask changes and exposes the tick data through the Python API. citeturn891143search0turn891143search8

The replay keeps historical quotes bounded in memory through a rolling daily cache. A quote must be found at or before the scheduled execution timestamp within an explicit maximum staleness window; otherwise the hypothetical trade is marked unpriced rather than silently using a future or distant quote. This avoids introducing forward-looking quote bias.

Slippage, commission, and financing remain explicit assumptions for hypothetical trades. Real broker deal commission/swap records cannot be transferred to an unrelated hypothetical trade. Therefore the tick-aware replay can establish spread-aware execution pricing, but its net economics remain assumption-dependent until those assumptions are independently justified.

This replay is still research-only. It does not submit orders, write the model registry, or authorize promotion.
