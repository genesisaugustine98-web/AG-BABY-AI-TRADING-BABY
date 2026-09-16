# Empirical research gate

This gate defines what counts as evidence for an FX hypothesis in AG-BABY.

## Required sequence

1. Source acquisition with raw-payload hash.
2. Canonical normalization with source/version identifiers.
3. Point-in-time availability enforcement.
4. Fixed hypothesis specification before result inspection.
5. Chronological development, validation, and holdout segmentation.
6. Cost and delay stress.
7. Detailed outcome diagnostics including sample size, mean return, dispersion, win rate, profit factor, and drawdown.
8. Failure analysis and sensitivity to reasonable perturbations.
9. Reproducible artifact and configuration manifest.

## H.10-specific limitation

H.10 is daily bilateral reference-rate data. It is not executable dealer/venue bid-ask data and cannot establish live execution quality, depth, spread, rejection, or market impact. Historical values retrieved from the current historical table may reflect later revisions. Therefore an H.10-only result must be labeled as reference-rate evidence and revised-history evidence unless independent historical vintages are available.

## Promotion rule

No model is promoted from research on the basis of in-sample return alone. A result is a research observation until it survives the locked holdout, cost stress, and falsification checks. A result that does not survive is retained as negative evidence rather than tuned away.
