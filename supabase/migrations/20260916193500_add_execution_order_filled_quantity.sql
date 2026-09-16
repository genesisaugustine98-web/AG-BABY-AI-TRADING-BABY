alter table public.execution_orders
  add column if not exists filled_quantity numeric not null default 0;
