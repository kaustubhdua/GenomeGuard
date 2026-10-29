-- Tighten consent withdrawal to the dedicated consent_steward role only.
-- Ordinary reviewers and organization administrators do not inherit consent authority.

create or replace function public.gg_withdraw_consent(
  p_auth_user_id uuid,
  p_consent_id uuid,
  p_reason text
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $withdraw_consent$
declare
  v_membership genomeguard.organization_memberships%rowtype;
  v_consent genomeguard.participant_consent_records%rowtype;
begin
  if p_auth_user_id is null or p_consent_id is null
     or p_reason is null or length(btrim(p_reason)) < 3 or length(btrim(p_reason)) > 1000 then
    raise exception 'invalid_consent_withdrawal' using errcode = '22023';
  end if;
  select m.* into v_membership
  from genomeguard.organization_memberships m
  join genomeguard.organizations o on o.id=m.organization_id
  where m.auth_user_id=p_auth_user_id and m.status='active' and o.status='active'
    and m.role = 'consent_steward'
  order by m.organization_id
  limit 1;
  if not found then
    raise exception 'active_consent_steward_membership_required' using errcode = '42501';
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
$withdraw_consent$;
revoke all on function public.gg_withdraw_consent(uuid,uuid,text) from public, anon, authenticated;
grant execute on function public.gg_withdraw_consent(uuid,uuid,text) to service_role;

comment on column genomeguard.organization_memberships.role is
  'Server-provisioned role. Consent withdrawal requires consent_steward or organization_admin; reviewer is not sufficient.';