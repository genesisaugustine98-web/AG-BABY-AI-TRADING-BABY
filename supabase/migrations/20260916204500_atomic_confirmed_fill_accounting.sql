create or replace function public.apply_broker_confirmed_fill(
  p_environment text, p_fill_id text, p_order_id text, p_broker_fill_id text,
  p_broker_order_id text, p_client_order_id text, p_instrument text, p_side text,
  p_quantity numeric, p_price numeric, p_filled_at timestamptz, p_broker text,
  p_commission numeric default 0, p_financing numeric default 0, p_metadata jsonb default '{}'::jsonb)
returns table(duplicate boolean, position_id text, instrument text, net_quantity numeric,
              average_price numeric, realized_pnl numeric, financing_pnl numeric, state text)
language plpgsql
security invoker
set search_path = public
as $$
declare
  v_side text := upper(trim(p_side));
  v_db_side text := lower(trim(p_side));
  v_existing_fill public.execution_fills%rowtype;
  v_position public.execution_positions%rowtype;
  v_order public.execution_orders%rowtype;
  v_delta numeric;
  v_qty numeric;
  v_new_qty numeric;
  v_closing numeric;
  v_pnl numeric;
  v_realized numeric;
  v_avg numeric;
  v_new_filled numeric;
  v_position_key text := p_environment || ':' || p_instrument;
  v_payload jsonb;
  v_prev_hash text;
  v_event_hash text;
begin
  if p_environment not in ('demo','paper','live') then raise exception 'invalid environment'; end if;
  if p_fill_id is null or length(trim(p_fill_id)) = 0 then raise exception 'fill_id is required'; end if;
  if p_order_id is null or length(trim(p_order_id)) = 0 then raise exception 'order_id is required'; end if;
  if p_broker_order_id is null or length(trim(p_broker_order_id)) = 0 then raise exception 'broker_order_id is required'; end if;
  if p_client_order_id is null or length(trim(p_client_order_id)) = 0 then raise exception 'client_order_id is required'; end if;
  if p_instrument is null or length(trim(p_instrument)) = 0 then raise exception 'instrument is required'; end if;
  if v_side not in ('BUY','SELL') then raise exception 'unsupported fill side'; end if;
  if p_quantity <= 0 then raise exception 'fill quantity must be positive'; end if;
  if p_price <= 0 then raise exception 'fill price must be positive'; end if;
  if p_commission < 0 then raise exception 'commission must be nonnegative'; end if;
  if p_financing < 0 then raise exception 'financing must be nonnegative'; end if;

  select eo.* into v_order
  from public.execution_orders eo
  where eo.order_id = p_order_id
  for update;
  if not found then raise exception 'internal order not found'; end if;
  if v_order.environment <> p_environment then raise exception 'order environment mismatch'; end if;
  if v_order.instrument <> p_instrument then raise exception 'order instrument mismatch'; end if;
  if lower(coalesce(v_order.side,'')) <> v_db_side then raise exception 'order side mismatch'; end if;
  if coalesce(v_order.client_order_id,'') <> p_client_order_id then raise exception 'client_order_id mismatch'; end if;
  if v_order.broker_order_id is not null and v_order.broker_order_id <> p_broker_order_id then raise exception 'broker_order_id mismatch'; end if;

  perform pg_advisory_xact_lock(hashtext(p_environment || ':' || p_instrument));

  select ef.* into v_existing_fill
  from public.execution_fills ef
  where ef.fill_id = p_fill_id
     or (ef.broker_fill_id is not null and p_broker_fill_id is not null
         and ef.order_id = p_order_id and ef.broker_fill_id = p_broker_fill_id)
  limit 1;

  if found then
    select ep.* into v_position from public.execution_positions ep where ep.position_id = v_position_key;
    if not found then raise exception 'duplicate fill exists but position state is missing'; end if;
    return query select true, v_position.position_id, v_position.instrument,
      v_position.net_quantity, coalesce(v_position.average_price,0),
      v_position.realized_pnl, v_position.financing_pnl, v_position.state;
    return;
  end if;

  v_new_filled := coalesce(v_order.filled_quantity,0) + p_quantity;
  if v_new_filled > v_order.requested_quantity then
    raise exception 'fill quantity exceeds requested order quantity';
  end if;

  insert into public.execution_fills(
    fill_id, order_id, broker_fill_id, filled_at, quantity, price, side,
    venue, commission, financing, metadata)
  values (
    p_fill_id, p_order_id, p_broker_fill_id, p_filled_at, p_quantity, p_price,
    v_db_side, p_broker, p_commission, p_financing, coalesce(p_metadata,'{}'::jsonb));

  select ep.* into v_position
  from public.execution_positions ep
  where ep.position_id = v_position_key
  for update;

  if not found then
    insert into public.execution_positions(
      position_id, environment, instrument, net_quantity, average_price,
      realized_pnl, financing_pnl, state, metadata)
    values (v_position_key, p_environment, p_instrument, 0, 0, 0, 0, 'FLAT', '{}'::jsonb)
    returning * into v_position;
  end if;

  v_qty := v_position.net_quantity;
  v_realized := v_position.realized_pnl;
  v_delta := case when v_side='BUY' then p_quantity else -p_quantity end;

  if v_qty = 0 then
    v_new_qty := v_delta;
    v_avg := p_price;
  elsif (v_qty > 0 and v_delta > 0) or (v_qty < 0 and v_delta < 0) then
    v_new_qty := v_qty + v_delta;
    v_avg := ((abs(v_qty) * coalesce(v_position.average_price,0))
             + (abs(v_delta) * p_price)) / (abs(v_qty) + abs(v_delta));
  else
    v_closing := least(abs(v_qty), abs(v_delta));
    v_pnl := v_closing * (p_price - coalesce(v_position.average_price,0))
             * case when v_qty > 0 then 1 else -1 end;
    v_realized := v_realized + v_pnl - p_commission;
    v_new_qty := v_qty + v_delta;
    if v_new_qty = 0 then
      v_avg := 0;
    elsif (v_qty > 0 and v_new_qty > 0) or (v_qty < 0 and v_new_qty < 0) then
      v_avg := coalesce(v_position.average_price,0);
    else
      v_avg := p_price;
    end if;
  end if;

  if v_qty = 0 or ((v_qty > 0 and v_delta > 0) or (v_qty < 0 and v_delta < 0)) then
    v_realized := v_realized - p_commission;
  end if;

  update public.execution_positions ep
  set net_quantity = v_new_qty,
      average_price = case when v_new_qty = 0 then 0 else v_avg end,
      realized_pnl = v_realized,
      financing_pnl = coalesce(v_position.financing_pnl,0) + p_financing,
      state = case when v_new_qty = 0 then 'FLAT' else 'OPEN' end,
      last_reconciled_at = null,
      updated_at = now()
  where ep.position_id = v_position_key;

  update public.execution_orders eo
  set filled_quantity = v_new_filled,
      state = case when v_new_filled = v_order.requested_quantity
                   then 'FILLED' else 'PARTIALLY_FILLED' end,
      last_broker_update_at = p_filled_at,
      updated_at = now()
  where eo.order_id = p_order_id;

  select ep.* into v_position from public.execution_positions ep where ep.position_id = v_position_key;

  v_payload := jsonb_build_object(
    'fill_id',p_fill_id,'order_id',p_order_id,'broker_fill_id',p_broker_fill_id,
    'broker_order_id',p_broker_order_id,'client_order_id',p_client_order_id,
    'instrument',p_instrument,'side',v_side,'quantity',p_quantity,'price',p_price,
    'filled_at',p_filled_at,'broker',p_broker,'commission',p_commission,
    'financing',p_financing,'metadata',coalesce(p_metadata,'{}'::jsonb),'confirmed',true);

  select ee.event_hash into v_prev_hash
  from public.execution_events ee
  where ee.environment=p_environment and ee.correlation_id=p_client_order_id
  order by ee.occurred_at desc, ee.created_at desc
  limit 1;

  v_event_hash := encode(
    extensions.digest(
      convert_to(jsonb_build_object(
        'event_type','BROKER_CONFIRMED_FILL',
        'correlation_id',p_client_order_id,
        'payload',v_payload,
        'previous_event_hash',v_prev_hash)::text,'UTF8'),
      'sha256'::text),
    'hex');

  insert into public.execution_events(
    event_id,occurred_at,environment,event_type,correlation_id,order_id,
    broker_order_id,position_id,payload,source,source_version,previous_event_hash,event_hash)
  values(
    gen_random_uuid(),p_filled_at,p_environment,'BROKER_CONFIRMED_FILL',
    p_client_order_id,p_order_id,p_broker_order_id,v_position_key,v_payload,
    p_broker,'accounting-v2',v_prev_hash,v_event_hash);

  return query select false,v_position.position_id,v_position.instrument,
    v_position.net_quantity,coalesce(v_position.average_price,0),
    v_position.realized_pnl,v_position.financing_pnl,v_position.state;
end;
$$;

revoke execute on function public.apply_broker_confirmed_fill(text,text,text,text,text,text,text,text,numeric,numeric,timestamptz,text,numeric,numeric,jsonb)
from public, anon, authenticated;
grant execute on function public.apply_broker_confirmed_fill(text,text,text,text,text,text,text,text,numeric,numeric,timestamptz,text,numeric,numeric,jsonb)
to service_role;
