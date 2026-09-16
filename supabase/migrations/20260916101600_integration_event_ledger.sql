create table if not exists public.integration_events (
  id bigint generated always as identity primary key,
  schema_version text not null,
  repo text not null,
  commit_sha text not null,
  integration_name text not null,
  run_id text not null,
  correlation_id text not null,
  environment text not null check (environment in ('research','paper','demo','live')),
  status text not null check (status in ('queued','running','success','failed','blocked')),
  started_at timestamptz not null,
  completed_at timestamptz not null,
  artifact_uri text,
  failure_class text,
  created_at timestamptz not null default now()
);

create index if not exists integration_events_correlation_idx
  on public.integration_events (correlation_id);

create index if not exists integration_events_commit_idx
  on public.integration_events (commit_sha);

create index if not exists integration_events_created_idx
  on public.integration_events (created_at desc);

alter table public.integration_events enable row level security;

-- No public INSERT/UPDATE/DELETE policies are granted.
-- Trusted server-side publishers must use the Supabase service-role key.
