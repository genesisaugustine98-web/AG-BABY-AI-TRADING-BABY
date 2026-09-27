-- Institutional control-plane schema. Service-role only by design.

create table if not exists public.execution_account_snapshots (
  snapshot_id uuid primary key default gen_random_uuid(),
  environment text not null check (environment in ('paper','demo','live')),
  captured_at timestamptz not null,
  broker text not null,
  account_login text,
  server text,
  currency text,
  balance numeric not null,
  equity numeric not null,
  margin numeric,
  margin_free numeric,
  margin_level numeric,
  trade_allowed boolean,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists execution_account_snapshots_env_time_idx
  on public.execution_account_snapshots(environment, captured_at desc);

create table if not exists public.risk_limits (
  environment text primary key check (environment in ('paper','demo','live')),
  max_order_risk numeric not null check (max_order_risk between 0 and 1),
  max_strategy_risk numeric not null check (max_strategy_risk between 0 and 1),
  max_gross_risk numeric not null check (max_gross_risk between 0 and 1),
  max_drawdown numeric not null check (max_drawdown between 0 and 1),
  max_daily_loss numeric not null check (max_daily_loss between 0 and 1),
  max_open_positions integer not null check (max_open_positions >= 1),
  min_broker_health numeric not null check (min_broker_health between 0 and 1),
  min_data_health numeric not null check (min_data_health between 0 and 1),
  policy_version text not null,
  updated_at timestamptz not null default now()
);

insert into public.risk_limits(environment,max_order_risk,max_strategy_risk,max_gross_risk,max_drawdown,max_daily_loss,max_open_positions,min_broker_health,min_data_health,policy_version)
values
 ('demo',0.01,0.02,0.03,0.08,0.03,8,0.80,0.80,'risk-v1'),
 ('paper',0.01,0.02,0.03,0.08,0.03,8,0.80,0.80,'risk-v1'),
 ('live',0.0,0.0,0.0,0.0,0.0,1,1.0,1.0,'live-disabled')
on conflict (environment) do nothing;

create table if not exists public.risk_decisions (
  decision_id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  environment text not null check (environment in ('paper','demo','live')),
  intent_id text not null,
  order_id text,
  decision text not null check (decision in ('APPROVE','DENY','REVIEW')),
  reasons jsonb not null default '[]'::jsonb,
  estimated_loss numeric,
  order_risk_fraction numeric,
  projected_gross_risk_fraction numeric,
  policy_version text,
  model_id text,
  model_version text,
  evidence_ids jsonb not null default '[]'::jsonb,
  payload jsonb not null default '{}'::jsonb
);
create index if not exists risk_decisions_env_created_idx on public.risk_decisions(environment, created_at desc);

create table if not exists public.model_registry (
  model_id text not null,
  version text not null,
  status text not null check (status in ('candidate','validated','production','retired','blocked')),
  artifact_uri text,
  dataset_fingerprint text,
  code_commit_sha text,
  metrics jsonb not null default '{}'::jsonb,
  calibration jsonb not null default '{}'::jsonb,
  feature_version text,
  created_at timestamptz not null default now(),
  retired_at timestamptz,
  primary key(model_id, version)
);

create table if not exists public.research_runs (
  run_id text primary key,
  hypothesis_id text,
  dataset_fingerprint text,
  code_commit_sha text,
  config jsonb not null default '{}'::jsonb,
  status text not null check (status in ('queued','running','success','failed','blocked')),
  started_at timestamptz not null,
  completed_at timestamptz,
  artifact_uri text,
  summary jsonb not null default '{}'::jsonb
);
create index if not exists research_runs_status_idx on public.research_runs(status, started_at desc);

create table if not exists public.opportunity_candidates (
  candidate_id text primary key,
  created_at timestamptz not null default now(),
  environment text not null check (environment in ('research','paper','demo','live')),
  instrument text not null,
  side text not null check (side in ('BUY','SELL')),
  expected_return numeric,
  probability_up numeric check (probability_up between 0 and 1),
  calibration_score numeric check (calibration_score between 0 and 1),
  estimated_cost numeric,
  executable_edge numeric,
  suggested_risk numeric,
  state text not null check (state in ('NEW','VALIDATING','ADMITTED','REJECTED','EXPIRED','EXECUTED')),
  model_id text,
  model_version text,
  evidence_ids jsonb not null default '[]'::jsonb,
  market_state jsonb not null default '{}'::jsonb,
  payload jsonb not null default '{}'::jsonb
);
create index if not exists opportunity_candidates_env_created_idx on public.opportunity_candidates(environment, created_at desc);
create index if not exists opportunity_candidates_instrument_idx on public.opportunity_candidates(instrument, created_at desc);

create table if not exists public.data_source_registry (
  source_id text primary key,
  provider text not null,
  source_type text not null,
  license_class text not null,
  revision text,
  health numeric check (health between 0 and 1),
  last_seen_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

alter table public.execution_account_snapshots enable row level security;
alter table public.risk_limits enable row level security;
alter table public.risk_decisions enable row level security;
alter table public.model_registry enable row level security;
alter table public.research_runs enable row level security;
alter table public.opportunity_candidates enable row level security;
alter table public.data_source_registry enable row level security;

create policy execution_account_snapshots_deny_api on public.execution_account_snapshots for all to anon using (false) with check (false);
create policy risk_limits_deny_api on public.risk_limits for all to anon using (false) with check (false);
create policy risk_decisions_deny_api on public.risk_decisions for all to anon using (false) with check (false);
create policy model_registry_deny_api on public.model_registry for all to anon using (false) with check (false);
create policy research_runs_deny_api on public.research_runs for all to anon using (false) with check (false);
create policy opportunity_candidates_deny_api on public.opportunity_candidates for all to anon using (false) with check (false);
create policy data_source_registry_deny_api on public.data_source_registry for all to anon using (false) with check (false);

create policy execution_account_snapshots_deny_authenticated on public.execution_account_snapshots for all to authenticated using (false) with check (false);
create policy risk_limits_deny_authenticated on public.risk_limits for all to authenticated using (false) with check (false);
create policy risk_decisions_deny_authenticated on public.risk_decisions for all to authenticated using (false) with check (false);
create policy model_registry_deny_authenticated on public.model_registry for all to authenticated using (false) with check (false);
create policy research_runs_deny_authenticated on public.research_runs for all to authenticated using (false) with check (false);
create policy opportunity_candidates_deny_authenticated on public.opportunity_candidates for all to authenticated using (false) with check (false);
create policy data_source_registry_deny_authenticated on public.data_source_registry for all to authenticated using (false) with check (false);
