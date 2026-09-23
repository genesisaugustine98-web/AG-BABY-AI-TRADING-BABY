# Change Control and Release Discipline

Institutional-style execution requires the software artifact to be as controlled as the order itself.

## Required release identity

Every autonomous runtime must identify:

- Git commit SHA
- model ID and model version
- dataset fingerprint
- feature version
- policy version
- runtime instance ID
- configuration fingerprint
- deployment environment

Secrets are excluded from the configuration fingerprint.

## Change classes

### Research-only

Does not touch execution behavior. Still requires deterministic tests and evidence lineage.

### Execution-control

Changes risk, allocation, order state, reconciliation, broker adapters, durable accounting or freeze behavior. Requires targeted tests plus the complete safety suite.

### Deployment/security

Changes credentials, host supervision, network policy, CI, release or database permissions. Requires the relevant deployment/security validation before promotion.

## Release invariant

A version that fails safety tests is not promotable.

A version that changes execution semantics must have a new commit identity and must not silently reuse a previous model/evidence artifact.

## Rollback

Rollback is a versioned artifact transition, not an ad-hoc file edit. After rollback:

1. Stop autonomous submission.
2. Reconcile broker truth.
3. Verify the target commit/model/config identity.
4. Rebuild local risk reservations.
5. Resume only after a clean reconciliation.

## Database changes

Database DDL is represented by versioned migrations. Any new execution/control table must have appropriate RLS and privileged access must remain server-side.

## Promotion boundary

This repository does not authorize live capital. Any future capital-enabled environment must be implemented as a separately reviewed deployment boundary, not by changing a single environment variable in the canonical demo runtime.
