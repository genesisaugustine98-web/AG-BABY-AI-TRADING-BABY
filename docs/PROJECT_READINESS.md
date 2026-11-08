# Project readiness

Review date: 8 November 2026.

## Scope

An evidence-first FX research, decision, risk and demo-only execution framework. The repository explicitly separates architecture coverage from profitability and states that live trading is disabled.

## Implemented evidence in the repository

- Deterministic domain, policy, risk and state components.
- MT5 demo-only gateway that fails closed when demo-account status cannot be proven.
- Integration-health workflow observed passing in the recent audit.
- H.10 research/acquisition workflows had repeated failures on 7 November 2026; the root cause was missing repository-root import path when scripts were executed directly by path.

## Changes in this branch

- The two H.10 scripts now add the repository root to sys.path before importing the apps package. This addresses the observed ModuleNotFoundError: No module named 'apps' without changing experiment logic or data semantics.
- Workflow logs and the failing step names were reviewed before making the change.

## Not established

- No live trading, customer trading, broker production approval or independently audited returns are claimed.
- Backtest and research outputs require their own data provenance, reproducibility and independent review before they support a performance claim.
- No root repository licence file was found. Do not assume the code is MIT/open-source or reusable until the owner chooses a licence.
- No independent penetration test, broker certification or institutional control certification is claimed.

## Next evidence gates

1. Re-run the H.10 acquisition and experiment workflows from this branch.
2. Preserve raw source bytes, source hashes, release timestamps and experiment configuration with every research result.
3. Verify point-in-time availability and avoid treating later-revised H.10 values as data known at the original release time.
4. Validate broker execution, fill reconciliation and failure recovery only on an isolated demo account.
5. Obtain independent review of risk, reconciliation and strategy evaluation before any further deployment discussion.
