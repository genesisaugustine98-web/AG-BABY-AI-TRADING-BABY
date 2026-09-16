# Institutional FX Edge - Trading OS v2

**Author: Genesis Koodanga Augustine - September 2026**

This repository is the canonical engineering control plane for an evidence-first FX research, decision, risk and **demo-only** execution system.

## Important status

- This release targets **>=80% architectural coverage of the specified end-to-end system**, not 80% trading accuracy or profitability.
- Live trading is intentionally disabled by architecture in this v2 scaffold.
- The LLM has no execution credentials and no direct broker authority.
- Unknown broker results cannot transition directly to retry.
- Risk, admission and execution are separate interfaces.
- External platforms must consume versioned repository artifacts and must not become a second source of truth.

## Core flow

`data -> quality -> provenance -> state -> forecast -> executable value -> risk -> admission -> order state machine -> broker -> reconciliation -> TCA -> monitoring`

## Platform control plane

The integration layer defines one communication contract for GitHub, Hugging Face, Kaggle, Colab, AWS, Vercel, Supabase, Render, DigitalOcean, research libraries, and the MT5 demo gateway. See `integrations/PLATFORM_MATRIX.md` and `schemas/integration_event.schema.json`.

CI runs deterministic tests plus a secret-safe integration presence check. Credentials are never printed or committed.

## Repository structure

- `packages/` - deterministic domain/risk/policy/state/audit primitives
- `apps/execution_gateway/` - MT5 adapter + deterministic broker test double
- `tests/` - safety and state tests
- `configs/` - demo-only environment template
- `integrations/` - platform matrix, environment template, and health checker
- `schemas/` - versioned interoperability contracts
- `docs/` - engineering specifications and the master cookbook

## Credential rule

Never commit broker passwords/API keys. Use an OS secret store, cloud secret manager, or protected platform secret store. Prefer GitHub OIDC for cloud deployments where supported. The LLM must never receive broker credentials.

## MT5 demo path

Install the optional trading dependency on a Windows host with the MT5 terminal available. Configure the demo server allowlist and credentials outside Git. The gateway refuses execution unless the account can be positively verified as demo.

## Development gate

Before any unattended demo execution is enabled, implement broker reconciliation, exact contract validation, persistent idempotency/UNKNOWN-state recovery, kill switches, real TCA/markouts, deterministic replay, fault injection, and paper/demo promotion gates.

## Research doctrine

A strategy is not promoted because it looks good in-sample. Require point-in-time data, OOS evaluation, costs, delay, parameter perturbation, regime analysis, stress events, calibration, shadow/paper/demo evidence, and a predefined retirement condition.

## Sources / design basis

See the companion cookbook and research volumes for the full evidence map. The architecture preserves the distinction between observed institutional mechanisms, empirical findings, engineering proposals and unverified claims.
