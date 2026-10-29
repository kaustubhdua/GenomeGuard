-- Request detail/history read path. It never returns genotype calls or untransformed dataset rows.
create or replace function public.gg_get_request_details(
  p_auth_user_id uuid,
  p_request_id bigint
) returns jsonb
language plpgsql
stable
security definer
set search_path = ''
as $request_details$
declare
  v_membership genomeguard.organization_memberships%rowtype;
  v_request genomeguard.requests%rowtype;
  v_requester_auth uuid;
  v_decision jsonb;
  v_history jsonb;
begin
  if p_auth_user_id is null or p_request_id is null then
    raise exception 'invalid_request_lookup' using errcode = '22023';
  end if;
  select * into v_request
  from genomeguard.requests
  where id=p_request_id;
  if not found then
    raise exception 'request_not_found' using errcode = 'P0002';
  end if;
  select m.* into v_membership
  from genomeguard.organization_memberships m
  join genomeguard.organizations o on o.id=m.organization_id
  where m.auth_user_id=p_auth_user_id and m.organization_id=v_request.organization_id
    and m.status='active' and o.status='active'
  limit 1;
  if not found then
    raise exception 'request_not_found' using errcode = 'P0002';
  end if;
  select r.auth_user_id into v_requester_auth
  from genomeguard.requesters r where r.id=v_request.requester_id;
  if v_membership.role='researcher' and v_requester_auth is distinct from p_auth_user_id then
    raise exception 'request_not_found' using errcode = 'P0002';
  end if;
  select case when d.id is null then null else jsonb_build_object(
    'id',d.id,'outcome',d.outcome,'reasons',coalesce(d.reasons_json,'[]')::jsonb,
    'explanation',d.explanation_text,'needs_human',coalesce(d.needs_human,1)=1,
    'reviewed_at',d.reviewed_at
  ) end into v_decision
  from genomeguard.decisions d where d.request_id=p_request_id;
  select coalesce(jsonb_agg(jsonb_build_object(
    'event_type',e.event_type,'outcome',e.outcome,'created_at',e.created_at,'details',e.details
  ) order by e.created_at),'[]'::jsonb) into v_history
  from genomeguard.api_events e where e.request_id=p_request_id
    and e.auth_user_id is not null;
  return jsonb_build_object(
    'request',jsonb_build_object(
      'id',v_request.id,'created_at',v_request.ts,'purpose',v_request.purpose,
      'disease',v_request.disease,'is_commercial',v_request.is_commercial=1,
      'data_level',v_request.data_level,'status',v_request.status,
      'cohort_filter',v_request.cohort_filter_json::jsonb,
      'variant_filter',v_request.variant_filter_json::jsonb,
      'organization_id',v_request.organization_id
    ),
    'decision',v_decision,
    'history',v_history,
    'release_status','not_released_by_request_detail_api'
  );
end;
$request_details$;
revoke all on function public.gg_get_request_details(uuid,bigint) from public, anon, authenticated;
grant execute on function public.gg_get_request_details(uuid,bigint) to service_role;
