-- Resolve authorization against the target request/consent organization, not the user's first membership.
-- This supports multi-organization users without arbitrary organization selection or cross-org access.
CREATE OR REPLACE FUNCTION public.gg_review_request(p_auth_user_id uuid, p_request_id bigint, p_outcome text, p_reason text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_membership genomeguard.organization_memberships%rowtype;
  v_request genomeguard.requests%rowtype;
  v_decision_id bigint;
  v_status text;
begin
  if p_auth_user_id is null or p_request_id is null
     or p_outcome not in ('approved','denied','needs_more_information')
     or p_reason is null or length(btrim(p_reason)) < 3 or length(btrim(p_reason)) > 2000 then
    raise exception 'invalid_review' using errcode = '22023';
  end if;

  select * into v_request from genomeguard.requests where id=p_request_id;
  if not found then
    raise exception 'request_not_found' using errcode = 'P0002';
  end if;

  select m.* into v_membership
  from genomeguard.organization_memberships m
  join genomeguard.organizations o on o.id=m.organization_id
  where m.auth_user_id=p_auth_user_id and m.organization_id=v_request.organization_id
    and m.status='active' and o.status='active'
    and m.role in ('reviewer','organization_admin');
  if not found then
    raise exception 'request_not_found' using errcode = 'P0002';
  end if;

  select * into v_request from genomeguard.requests
    where id=p_request_id and organization_id=v_membership.organization_id
    for update;
  if not found then
    raise exception 'request_not_found' using errcode = 'P0002';
  end if;
  if v_request.status not in ('pending_review','needs_more_information') then
    raise exception 'request_not_reviewable' using errcode = '55000';
  end if;

  insert into genomeguard.decisions(request_id,outcome,reasons_json,explanation_text,
      needs_human,reviewed_by,reviewed_at)
  values (p_request_id,p_outcome,jsonb_build_array(btrim(p_reason))::text,btrim(p_reason),
      0,p_auth_user_id::text,now()::text)
  on conflict (request_id) do update set outcome=excluded.outcome,
      reasons_json=excluded.reasons_json, explanation_text=excluded.explanation_text,
      needs_human=0, reviewed_by=excluded.reviewed_by, reviewed_at=excluded.reviewed_at
  returning id into v_decision_id;

  insert into genomeguard.request_review_history(
      request_id,organization_id,reviewer_auth_user_id,previous_status,outcome,reason,decision_id
  ) values (
      p_request_id,v_request.organization_id,p_auth_user_id,v_request.status,p_outcome,btrim(p_reason),v_decision_id
  );

  v_status := case when p_outcome='needs_more_information' then 'needs_more_information'
                   when p_outcome='approved' then 'approved_pending_release'
                   else 'denied' end;
  update genomeguard.requests set status=v_status where id=p_request_id;

  insert into genomeguard.api_events(auth_user_id,event_type,request_id,outcome,details)
  values (p_auth_user_id,'research_request_reviewed',p_request_id,p_outcome,
    jsonb_build_object('decision_id',v_decision_id,'reason',btrim(p_reason),
      'organization_id',v_membership.organization_id,'previous_status',v_request.status,
      'new_status',v_status));

  return jsonb_build_object('request_id',p_request_id,'decision_id',v_decision_id,
    'outcome',p_outcome,'status',v_status,
    'message','Review decision recorded. Approval does not itself release genomic data.');
end;
$function$;

revoke all on function public.gg_review_request(uuid,bigint,text,text) from public, anon, authenticated;
grant execute on function public.gg_review_request(uuid,bigint,text,text) to service_role;

CREATE OR REPLACE FUNCTION public.gg_withdraw_consent(p_auth_user_id uuid, p_consent_id uuid, p_reason text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_membership genomeguard.organization_memberships%rowtype;
  v_consent genomeguard.participant_consent_records%rowtype;
begin
  if p_auth_user_id is null or p_consent_id is null
     or p_reason is null or length(btrim(p_reason)) < 3 or length(btrim(p_reason)) > 1000 then
    raise exception 'invalid_consent_withdrawal' using errcode = '22023';
  end if;
  select * into v_consent
  from genomeguard.participant_consent_records
  where id=p_consent_id;
  if not found then
    raise exception 'consent_record_not_found' using errcode = 'P0002';
  end if;

  select m.* into v_membership
  from genomeguard.organization_memberships m
  join genomeguard.organizations o on o.id=m.organization_id
  where m.auth_user_id=p_auth_user_id and m.organization_id=v_consent.organization_id
    and m.status='active' and o.status='active'
    and m.role = 'consent_steward';
  if not found then
    raise exception 'consent_record_not_found' using errcode = 'P0002';
  end if;

  select * into v_consent
  from genomeguard.participant_consent_records
  where id=p_consent_id and organization_id=v_membership.organization_id
  for update;
  if not found then
    raise exception 'consent_record_not_found' using errcode = 'P0002';
  end if;
  if v_consent.status in ('withdrawn','revoked','expired') then
    return jsonb_build_object('consent_id',p_consent_id,'status',v_consent.status,
      'message','Consent is already inactive; no data access was granted.');
  end if;
  update genomeguard.participant_consent_records
    set status='withdrawn', withdrawn_at=now(), updated_at=now()
    where id=p_consent_id;
  insert into genomeguard.api_events(auth_user_id,event_type,outcome,details)
  values (p_auth_user_id,'participant_consent_withdrawn','withdrawn',
    jsonb_build_object('consent_id',p_consent_id,'organization_id',v_membership.organization_id,
      'reason',btrim(p_reason)));
  return jsonb_build_object('consent_id',p_consent_id,'status','withdrawn',
    'message','Withdrawal recorded. Downstream release controls must enforce this status.');
end;
$function$;

revoke all on function public.gg_withdraw_consent(uuid,uuid,text) from public, anon, authenticated;
grant execute on function public.gg_withdraw_consent(uuid,uuid,text) to service_role;