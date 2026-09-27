drop policy if exists execution_ingestion_checkpoints_anon_deny on public.execution_ingestion_checkpoints;
create policy execution_ingestion_checkpoints_anon_deny on public.execution_ingestion_checkpoints for all to anon using (false) with check (false);
drop policy if exists execution_ingestion_checkpoints_authenticated_deny on public.execution_ingestion_checkpoints;
create policy execution_ingestion_checkpoints_authenticated_deny on public.execution_ingestion_checkpoints for all to authenticated using (false) with check (false);
revoke all on public.execution_ingestion_checkpoints from anon, authenticated;
grant select, insert, update, delete on public.execution_ingestion_checkpoints to service_role;

insert into public.execution_control_state(environment,frozen,reason)
values
  ('demo',true,'BOOTSTRAP_REQUIRED'),
  ('paper',true,'BOOTSTRAP_REQUIRED'),
  ('live',true,'LIVE_DISABLED')
on conflict (environment) do nothing;
