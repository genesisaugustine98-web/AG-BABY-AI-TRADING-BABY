create or replace function public.reject_execution_event_mutation()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
begin
  raise exception 'execution_events is append-only';
end;
$$;

drop trigger if exists execution_events_append_only on public.execution_events;

create trigger execution_events_append_only
before update or delete on public.execution_events
for each row
execute function public.reject_execution_event_mutation();

revoke execute on function public.reject_execution_event_mutation() from public, anon, authenticated;
grant execute on function public.reject_execution_event_mutation() to service_role;
