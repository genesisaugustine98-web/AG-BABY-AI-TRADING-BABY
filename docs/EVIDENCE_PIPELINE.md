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
