create table if not exists public.runtime_leases (
  lease_name text primary key,
  environment text not null check (environment = any (array['research','paper','demo']::text[])),
  owner_id text not null,
  fencing_token bigint not null default 0 check (fencing_token >= 0),
  acquired_at timestamptz not null default now(),
  renewed_at timestamptz not null default now(),
  lease_until timestamptz not null,
  metadata jsonb not null default '{}'::jsonb
);

alter table public.runtime_leases enable row level security;
revoke all on table public.runtime_leases from anon, authenticated;

create or replace function public.runtime_acquire_lease(
  p_lease_name text,
  p_environment text,
  p_owner_id text,
  p_ttl_seconds integer default 30
)
returns table (
  lease_name text,
  owner_id text,
  fencing_token bigint,
  lease_until timestamptz
)
language sql
security invoker
set search_path = public
as $$
  insert into public.runtime_leases (
    lease_name, environment, owner_id, fencing_token, acquired_at, renewed_at, lease_until
  )
  values (
    p_lease_name, p_environment, p_owner_id, 1, now(), now(),
    now() + make_interval(secs => greatest(p_ttl_seconds, 5))
  )
  on conflict (lease_name) do update
  set
    environment = excluded.environment,
    owner_id = excluded.owner_id,
    fencing_token = public.runtime_leases.fencing_token + 1,
    renewed_at = now(),
    lease_until = now() + make_interval(secs => greatest(p_ttl_seconds, 5))
  where public.runtime_leases.lease_until < now()
     or public.runtime_leases.owner_id = excluded.owner_id
  returning
    runtime_leases.lease_name,
    runtime_leases.owner_id,
    runtime_leases.fencing_token,
    runtime_leases.lease_until;
$$;

create or replace function public.runtime_renew_lease(
  p_lease_name text,
  p_owner_id text,
  p_fencing_token bigint,
  p_ttl_seconds integer default 30
)
returns table (
  lease_name text,
  owner_id text,
  fencing_token bigint,
  lease_until timestamptz
)
language sql
security invoker
set search_path = public
as $$
  update public.runtime_leases
  set
    renewed_at = now(),
    lease_until = now() + make_interval(secs => greatest(p_ttl_seconds, 5))
  where runtime_leases.lease_name = p_lease_name
    and runtime_leases.owner_id = p_owner_id
    and runtime_leases.fencing_token = p_fencing_token
    and runtime_leases.lease_until >= now()
  returning
    runtime_leases.lease_name,
    runtime_leases.owner_id,
    runtime_leases.fencing_token,
    runtime_leases.lease_until;
$$;

create or replace function public.runtime_release_lease(
  p_lease_name text,
  p_owner_id text,
  p_fencing_token bigint
)
returns boolean
language sql
security invoker
set search_path = public
as $$
  with deleted as (
    delete from public.runtime_leases
    where runtime_leases.lease_name = p_lease_name
      and runtime_leases.owner_id = p_owner_id
      and runtime_leases.fencing_token = p_fencing_token
    returning 1
  )
  select exists(select 1 from deleted);
$$;

revoke execute on function public.runtime_acquire_lease(text, text, text, integer) from public, anon, authenticated;
revoke execute on function public.runtime_renew_lease(text, text, bigint, integer) from public, anon, authenticated;
revoke execute on function public.runtime_release_lease(text, text, bigint) from public, anon, authenticated;

grant execute on function public.runtime_acquire_lease(text, text, text, integer) to service_role;
grant execute on function public.runtime_renew_lease(text, text, bigint, integer) to service_role;
grant execute on function public.runtime_release_lease(text, text, bigint) to service_role;

create index if not exists runtime_leases_until_idx on public.runtime_leases (lease_until);
