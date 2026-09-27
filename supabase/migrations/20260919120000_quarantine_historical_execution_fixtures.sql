-- Preserve historical test evidence while keeping synthetic fixtures out of canonical live/demo truth.
alter table public.execution_orders
  add column if not exists is_test_fixture boolean not null default false,
  add column if not exists quarantine_reason text;

alter table public.execution_positions
  add column if not exists is_test_fixture boolean not null default false,
  add column if not exists quarantine_reason text;

alter table public.execution_fills
  add column if not exists is_test_fixture boolean not null default false,
  add column if not exists quarantine_reason text;

update public.execution_orders
set is_test_fixture = true,
    quarantine_reason = 'historical_synthetic_fixture'
where order_id = 'acct-test-order-20260916'
  and environment = 'demo';

update public.execution_positions
set is_test_fixture = true,
    quarantine_reason = 'historical_synthetic_fixture'
where environment = 'demo'
  and instrument = 'TESTUSDJPY';

update public.execution_fills
set is_test_fixture = true,
    quarantine_reason = 'historical_synthetic_fixture'
where order_id = 'acct-test-order-20260916';

create index if not exists execution_orders_active_environment_idx
  on public.execution_orders(environment, is_test_fixture, state);

create index if not exists execution_positions_active_environment_idx
  on public.execution_positions(environment, is_test_fixture, instrument);
