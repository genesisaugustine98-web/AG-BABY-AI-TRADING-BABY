create table if not exists public.runtime_alerts (
  alert_id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  environment text not null check (environment in ('research','paper','demo')),
  severity text not null check (severity in ('INFO','WARN','ERROR','CRITICAL')),
  source text not null,
  alert_key text not null,
  correlation_id text not null,
  message text not null,
  payload jsonb not null default '{}'::jsonb
);
create index if not exists runtime_alerts_env_created_idx on public.runtime_alerts(environment,created_at desc);
create index if not exists runtime_alerts_key_created_idx on public.runtime_alerts(alert_key,created_at desc);
alter table public.runtime_alerts enable row level security;
drop policy if exists runtime_alerts_anon_deny on public.runtime_alerts;
create policy runtime_alerts_anon_deny on public.runtime_alerts for all to anon using (false) with check (false);
drop policy if exists runtime_alerts_authenticated_deny on public.runtime_alerts;
create policy runtime_alerts_authenticated_deny on public.runtime_alerts for all to authenticated using (false) with check (false);
revoke all on public.runtime_alerts from anon,authenticated;
grant select,insert on public.runtime_alerts to service_role;

create table if not exists public.model_surveillance_events (
  event_id uuid primary key default gen_random_uuid(),
  observed_at timestamptz not null default now(),
  environment text not null check (environment in ('paper','demo')),
  model_id text not null,
  version text not null,
  decision text not null check (decision in ('RETAIN','RETIRE')),
  breach_count integer not null check (breach_count >= 0),
  psi numeric,
  brier_score numeric,
  rolling_net_bps numeric,
  drawdown_fraction numeric,
  reasons jsonb not null default '[]'::jsonb,
  metrics jsonb not null default '{}'::jsonb
);
create index if not exists model_surveillance_identity_idx on public.model_surveillance_events(model_id,version,observed_at desc);
alter table public.model_surveillance_events enable row level security;
drop policy if exists model_surveillance_events_anon_deny on public.model_surveillance_events;
create policy model_surveillance_events_anon_deny on public.model_surveillance_events for all to anon using (false) with check (false);
drop policy if exists model_surveillance_events_authenticated_deny on public.model_surveillance_events;
create policy model_surveillance_events_authenticated_deny on public.model_surveillance_events for all to authenticated using (false) with check (false);
revoke all on public.model_surveillance_events from anon,authenticated;
grant select,insert on public.model_surveillance_events to service_role;

create or replace function public.prevent_control_plane_telemetry_mutation()
returns trigger language plpgsql set search_path=pg_catalog,public as $$
begin raise exception 'control-plane telemetry is append-only'; end;
$$;
drop trigger if exists runtime_alerts_append_only on public.runtime_alerts;
create trigger runtime_alerts_append_only before update or delete on public.runtime_alerts for each row execute function public.prevent_control_plane_telemetry_mutation();
drop trigger if exists model_surveillance_events_append_only on public.model_surveillance_events;
create trigger model_surveillance_events_append_only before update or delete on public.model_surveillance_events for each row execute function public.prevent_control_plane_telemetry_mutation();
