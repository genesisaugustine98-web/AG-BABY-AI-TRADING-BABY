# Research Battery

The first empirical battery is intentionally simple and falsifiable. It exists to establish whether broad directional effects are detectable before introducing richer features or machine learning.

## Predeclared hypotheses

- H1_MOMENTUM_1D: prior daily direction predicts the next daily direction.
- H2_REVERSAL_1D: prior daily direction predicts the opposite next daily direction.
- H3_MOMENTUM_5D: prior daily direction predicts the direction over the next five observations.
- H4_REVERSAL_5D: prior daily direction predicts the opposite direction over the next five observations.

Instruments are EURUSD_REFERENCE, GBPUSD_REFERENCE, and USDJPY_REFERENCE. Costs are evaluated at 0, 2, 5, and 10 bps one-way.

## Sample protocol

Use a chronological 60/20/20 development/validation/holdout split. The split is determined by observation order, not by choosing favorable calendar periods. The holdout is inspected only after the experiment specification and any development/validation selection are frozen.

## Required interpretation

A positive result is not sufficient evidence of executable alpha. H.10 observations are reference rates, not live bid/ask quotes. The historical table may also contain revisions. Therefore results support claims about the specified reference-series experiment only.

A result that disappears after realistic cost assumptions, delay assumptions, or a chronological holdout is recorded as a failed or inconclusive hypothesis rather than tuned away.

## Evidence requirements

Every result should preserve dataset identifier/hash, source version, release-vintage metadata, code revision, hypothesis identifier, horizon, cost assumption, split, sample count, average net return, cumulative net return, volatility, maximum drawdown, win rate, and profit factor where defined.
