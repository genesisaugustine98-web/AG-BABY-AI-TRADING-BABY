create table if not exists public.execution_control_state (
  environment text primary key,
  frozen boolean not null default true,
  reason text,
  updated_at timestamptz not null default now()
);

alter table public.execution_control_state enable row level security;

drop policy if exists execution_control_state_anon_deny on public.execution_control_state;
create policy execution_control_state_anon_deny on public.execution_control_state
for all to anon using (false) with check (false);

drop policy if exists execution_control_state_authenticated_deny on public.execution_control_state;
create policy execution_control_state_authenticated_deny on public.execution_control_state
for all to authenticated using (false) with check (false);

create or replace function public.set_execution_control_state_updated_at()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists execution_control_state_updated_at on public.execution_control_state;
create trigger execution_control_state_updated_at before update on public.execution_control_state
for each row execute function public.set_execution_control_state_updated_at();
