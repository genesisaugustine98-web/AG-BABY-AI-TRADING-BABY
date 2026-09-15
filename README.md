# Institutional FX Edge - Trading OS v2

**Author: Genesis Koodanga Augustine - September 2026**

This repository is an engineering scaffold for an evidence-first FX research, decision, risk and **demo-only** execution system.

## Important status

- This release targets **>=80% architectural coverage of the specified end-to-end system**, not 80% trading accuracy or profitability.
- Live trading is intentionally disabled by architecture in this v2 scaffold.
- The LLM has no execution credentials and no direct broker authority.
- Unknown broker results cannot transition directly to retry.
- Risk, admission and execution are separate interfaces.

## Core flow

`data -> quality -> provenance -> state -> forecast -> executable value -> risk -> admission -> order state machine -> broker -> reconciliation -> TCA -> monitoring`

## Repository structure

- `packages/` - deterministic domain/risk/policy/state/audit primitives
- `apps/execution_gateway/` - MT5 adapter + deterministic broker test double
- `tests/` - safety and state tests
- `configs/` - demo-only environment template
- `docs/` - engineering specifications and the master cookbook

## Credential rule

Never commit broker passwords/API keys. Use an OS secret store, cloud secret manager, or a protected local environment file. The LLM must never receive broker credentials.

## MT5 demo path

Install the optional trading dependency on a Windows host with the MT5 terminal available. Configure the demo server allowlist and credentials outside Git. The gateway refuses execution unless the account can be positively verified as demo.

## Development gate

Before any unattended demo execution is enabled, implement broker reconciliation, exact contract validation, persistent idempotency/UNKNOWN-state recovery, kill switches, real TCA/markouts, deterministic replay, fault injection, and paper/demo promotion gates.

## Research doctrine

A strategy is not promoted because it looks good in-sample. Require point-in-time data, OOS evaluation, costs, delay, parameter perturbation, regime analysis, stress events, calibration, shadow/paper/demo evidence, and a predefined retirement condition.

## Sources / design basis

See the companion cookbook and research volumes for the full evidence map. The architecture preserves the distinction between observed institutional mechanisms, empirical findings, engineering proposals and unverified claims.
