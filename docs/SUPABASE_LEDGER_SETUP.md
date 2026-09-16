# Supabase integration ledger

The repository and Supabase project share the `public.integration_events` contract.

## Runtime boundary

`integrations/supabase_ledger.py` is server-side code only. It requires:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

Never expose the service-role key in browser/client code, Vercel public variables, source control, notebooks, or logs.

## GitHub Actions

The `supabase-integration-ledger` workflow publishes a research-environment lifecycle event after a `main` push when both GitHub Actions secrets are present:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

When the secrets are absent, the workflow exits successfully without publishing anything.

## Safety boundary

`live` events are rejected by the publisher and by the repository dispatch workflow. This integration records platform state; it is not an order-execution path. MT5 remains demo-only unless a separate, explicit production control gate is introduced.

## Schema source of truth

The SQL migration is versioned at `supabase/migrations/20260916101600_integration_event_ledger.sql` and matches the deployed ledger table in the connected Supabase project.
