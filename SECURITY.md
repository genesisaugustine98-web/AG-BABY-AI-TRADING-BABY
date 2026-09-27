# Security Policy

## Scope

AG-BABY contains trading research, execution-control and operations code. Broker credentials, Supabase server keys and deployment secrets are sensitive and must never be committed to Git or exposed to the browser.

## Required controls

- MT5 credentials exist only on the trusted Windows execution host.
- Supabase secret/service keys are server-side only.
- No trading credentials are accepted from frontend request bodies.
- The canonical autonomous runtime accepts only the demo environment.
- The operations cockpit is read-only.
- Runtime metrics bind to loopback unless an operator deliberately builds a separate authenticated telemetry proxy.
- Durable execution state and broker truth are reconciled before autonomous submission.
- UNKNOWN execution outcomes freeze the execution path; they are never treated as harmless network errors.
- The runtime uses host-local singleton locking and can use a Postgres fenced lease for multi-host deployments.

## Credential rotation

Rotate broker and database credentials after any suspected exposure. Revoke the old secret first, then restart the affected trusted runtime and perform a fresh broker reconciliation.

## Incident response

1. Freeze durable execution control.
2. Preserve the runtime event ledger and broker history.
3. Establish broker positions/orders independently of client memory.
4. Reconcile the durable order ledger against broker truth.
5. Quarantine unexplained fills or position drift.
6. Record the incident and root cause.
7. Only then restore the demo runtime.

Never delete unexplained broker evidence merely to make the internal ledger appear clean.

## Reporting

Do not open public issues containing credentials, account identifiers, broker secrets, tokens or private operational data. Remove secrets and report the sanitized technical condition instead.
