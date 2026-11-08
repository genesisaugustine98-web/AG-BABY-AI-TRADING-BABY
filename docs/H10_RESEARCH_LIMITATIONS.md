# Federal Reserve H.10 research limitations

## What this data is

Federal Reserve H.10 daily foreign-exchange rates are reference rates. They are not executable bid/ask quotes and do not establish that a retail broker would have offered the price or fill.

## Required handling

- Preserve the exact raw download and SHA-256 hash.
- Preserve the source release date and timestamp separately from the observation date.
- Keep H.10 observations marked non-execution-grade.
- Apply conservative costs as a sensitivity analysis, but do not imply a single fixed cost captures broker spreads, slippage, financing, latency or market impact.
- Keep a strict chronological development/validation/holdout design.
- Report revisions and the historical-release limitation explicitly. A currently downloaded historical series can contain later revisions and is not automatically a point-in-time vintage.

## CI correction

Two H.10 workflows failed because direct script execution placed scripts/ rather than the repository root on sys.path. The scripts now explicitly insert the repository root before importing apps.research. This changes only package discovery; it does not repair or validate the underlying H.10 methodology.

## Interpretation

Passing acquisition and experiment workflows means the scripts ran successfully. It does not establish predictive edge, executable performance, a deployable trading strategy or suitability for live capital.
