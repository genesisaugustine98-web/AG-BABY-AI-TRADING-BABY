create table if not exists public.execution_tca (
  tca_id uuid primary key default gen_random_uuid(), observed_at timestamptz not null,
  environment text not null check (environment in ('paper','demo')), order_id text not null, broker_order_id text,
  strategy_id text not null, model_id text not null, model_version text not null, instrument text not null,
  side text not null check (side in ('BUY','SELL')), requested_quantity numeric not null check (requested_quantity > 0),
  filled_quantity numeric not null check (filled_quantity > 0), decision_mid numeric not null check (decision_mid > 0),
  execution_price numeric not null check (execution_price > 0), arrival_spread numeric not null check (arrival_spread >= 0),
  slippage_fraction numeric not null, slippage_bps numeric not null, spread_bps numeric not null,
  commission numeric not null check (commission >= 0), financing numeric not null, total_cost_fraction numeric not null,
  implementation_shortfall_quote numeric not null, metadata jsonb not null default '{}'::jsonb, created_at timestamptz not null default now()
);
create index if not exists execution_tca_env_observed_idx on public.execution_tca(environment, observed_at desc);
create index if not exists execution_tca_order_idx on public.execution_tca(order_id, observed_at desc);
alter table public.execution_tca enable row level security;
drop policy if exists execution_tca_anon_deny on public.execution_tca;
create policy execution_tca_anon_deny on public.execution_tca for all to anon using (false) with check (false);
drop policy if exists execution_tca_authenticated_deny on public.execution_tca;
create policy execution_tca_authenticated_deny on public.execution_tca for all to authenticated using (false) with check (false);
revoke all on public.execution_tca from anon, authenticated;
grant select,insert on public.execution_tca to service_role;
create or replace function public.prevent_execution_tca_mutation()
returns trigger language plpgsql set search_path = pg_catalog, public as $$
begin raise exception 'execution_tca is append-only'; end;
$$;
drop trigger if exists execution_tca_append_only on public.execution_tca;
create trigger execution_tca_append_only before update or delete on public.execution_tca for each row execute function public.prevent_execution_tca_mutation();
