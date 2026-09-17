create table if not exists public.execution_ingestion_checkpoints (
    environment text not null,
    source text not null,
    stream text not null,
    watermark_msc bigint not null default 0 check (watermark_msc >= 0),
    overlap_msc bigint not null default 5000 check (overlap_msc >= 0),
    updated_at timestamptz not null default now(),
    metadata jsonb not null default '{}'::jsonb,
    primary key (environment, source, stream)
);

alter table public.execution_ingestion_checkpoints enable row level security;

revoke all on public.execution_ingestion_checkpoints from anon, authenticated;
grant select, insert, update, delete on public.execution_ingestion_checkpoints to service_role;

create or replace function public.set_execution_ingestion_checkpoint_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists execution_ingestion_checkpoints_updated_at on public.execution_ingestion_checkpoints;
create trigger execution_ingestion_checkpoints_updated_at
before update on public.execution_ingestion_checkpoints
for each row execute function public.set_execution_ingestion_checkpoint_updated_at();
