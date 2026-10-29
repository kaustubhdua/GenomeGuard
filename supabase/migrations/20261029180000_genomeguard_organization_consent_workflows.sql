-- Authoritative organization membership and consent ledger.
-- No membership or consent rows are seeded. Until provisioned by a trusted administrator,
-- authenticated users cannot submit requests or perform reviewer actions.
create table if not exists genomeguard.organizations (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique check (slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
  display_name text not null check (length(trim(display_name)) between 2 and 200),
  status text not null default 'pending' check (status in ('pending','active','suspended','closed')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists genomeguard.organization_memberships (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references genomeguard.organizations(id) on delete restrict,
  auth_user_id uuid not null,
  role text not null check (role in ('researcher','reviewer','organization_admin')),
  status text not null default 'pending' check (status in ('pending','active','suspended','revoked')),
  invited_by uuid,
  activated_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, auth_user_id)
);
create index if not exists organization_memberships_user_status
  on genomeguard.organization_memberships(auth_user_id, status, organization_id);

alter table genomeguard.requests
  add column if not exists organization_id uuid references genomeguard.organizations(id) on delete restrict;
create index if not exists requests_org_status_id
  on genomeguard.requests(organization_id, status, id desc);

-- Consent records are explicitly evidence-backed and scoped. An empty table means no
-- participant-specific consent has been verified; public dataset policy is not a substitute.
create table if not exists genomeguard.participant_consent_records (
  id uuid primary key default gen_random_uuid(),
  donor_id integer not null references genomeguard.donors(id) on delete restrict,
  dataset_key text not null references genomeguard.variant_dataset_manifest(dataset_key) on delete restrict,
  organization_id uuid not null references genomeguard.organizations(id) on delete restrict,
  allowed_purposes text[] not null default '{}',
  allowed_data_levels text[] not null default '{}',
  status text not null check (status in ('pending_verification','active','withdrawn','expired','revoked')),
  evidence_reference text not null check (length(trim(evidence_reference)) between 3 and 500),
  verified_by uuid,
  verified_at timestamptz,
  effective_at timestamptz,
  expires_at timestamptz,
  withdrawn_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (cardinality(allowed_purposes) <= 100),
  check (cardinality(allowed_data_levels) <= 4),
  check (status <> 'active' or (verified_by is not null and verified_at is not null and effective_at is not null)),
  check (status <> 'withdrawn' or withdrawn_at is not null)
);
create index if not exists participant_consent_lookup
  on genomeguard.participant_consent_records(donor_id, dataset_key, organization_id, status);

alter table genomeguard.organizations enable row level security;
alter table genomeguard.organization_memberships enable row level security;
alter table genomeguard.participant_consent_records enable row level security;
revoke all on table genomeguard.organizations from public, anon, authenticated, service_role;
revoke all on table genomeguard.organization_memberships from public, anon, authenticated, service_role;
revoke all on table genomeguard.participant_consent_records from public, anon, authenticated, service_role;

-- The caller's organization and membership role come only from this server-side table,
-- never from the client-provided role/institution. Ambiguous multi-organization users fail closed.
create or replace function public.gg_submit_request(
  p_auth_user_id uuid,
  p_name text,
  p_institution text,
  p_purpose text,
  p_disease text,
  p_is_commercial boolean,
  p_data_level text,
  p_cohort_filter jsonb,
  p_variant_filter jsonb
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_membership genomeguard.organization_memberships%rowtype;
  v_org genomeguard.organizations%rowtype;
  v_membership_count integer;
  v_requester_id bigint;
  v_request_id bigint;
begin
  if p_auth_user_id is null
     or p_purpose is null or length(btrim(p_purpose)) < 3 or length(btrim(p_purpose)) > 500
     or p_data_level is null or p_data_level not in ('aggregate', 'frequency', 'variant', 'individual')
     or p_name is null or length(btrim(p_name)) < 2 or length(btrim(p_name)) > 120
     or p_institution is null or length(btrim(p_institution)) < 2 or length(btrim(p_institution)) > 200
     or p_is_commercial is null
     or (p_disease is not null and length(btrim(p_disease)) > 200)
     or jsonb_typeof(coalesce(p_cohort_filter, '{}'::jsonb)) <> 'object'
     or jsonb_typeof(coalesce(p_variant_filter, '{}'::jsonb)) <> 'object' then
    raise exception 'invalid_request' using errcode = '22023';
  end if;

  select count(*) into v_membership_count
  from genomeguard.organization_memberships m
  join genomeguard.organizations o on o.id=m.organization_id
  where m.auth_user_id=p_auth_user_id and m.status='active' and o.status='active'
    and m.role in ('researcher','reviewer','organization_admin');
  if v_membership_count = 0 then
    raise exception 'active_organization_membership_required' using errcode = '42501';
  elsif v_membership_count > 1 then
    raise exception 'explicit_organization_selection_required' using errcode = '22023';
  end if;

  select m.* into strict v_membership
  from genomeguard.organization_memberships m
  join genomeguard.organizations o on o.id=m.organization_id
  where m.auth_user_id=p_auth_user_id and m.status='active' and o.status='active'
    and m.role in ('researcher','reviewer','organization_admin');
  select * into strict v_org from genomeguard.organizations where id=v_membership.organization_id;

  insert into genomeguard.requesters(auth_user_id,name,role,credential_level,institution,created_at)
  values (p_auth_user_id,btrim(p_name),v_membership.role,'registered',v_org.display_name,now()::text)
  on conflict (auth_user_id) where auth_user_id is not null
  do update set name=excluded.name, role=excluded.role, credential_level='registered',
                institution=excluded.institution
  returning id into v_requester_id;

  insert into genomeguard.requests(requester_id,ts,purpose,disease,is_commercial,data_level,
      cohort_filter_json,variant_filter_json,status,organization_id)
  values (v_requester_id,now()::text,btrim(p_purpose),nullif(btrim(coalesce(p_disease,'')),''),
      case when p_is_commercial then 1 else 0 end,p_data_level,
      coalesce(p_cohort_filter,'{}'::jsonb)::text,coalesce(p_variant_filter,'{}'::jsonb)::text,
      'pending_review',v_org.id)
  returning id into v_request_id;

  insert into genomeguard.api_events(auth_user_id,event_type,request_id,outcome,details)
  values (p_auth_user_id,'research_request_submitted',v_request_id,'pending_review',
    jsonb_build_object('organization_id',v_org.id,'data_level',p_data_level,'commercial',p_is_commercial));
  return jsonb_build_object('id',v_request_id,'status','pending_review',
    'message','Request stored for steward review. No data access has been granted.');
end;
$$;
revoke all on function public.gg_submit_request(uuid,text,text,text,text,boolean,text,jsonb,jsonb) from public, anon, authenticated;
grant execute on function public.gg_submit_request(uuid,text,text,text,text,boolean,text,jsonb,jsonb) to service_role;

create or replace function public.gg_review_request(
  p_auth_user_id uuid,
  p_request_id bigint,
  p_outcome text,
  p_reason text
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_membership genomeguard.organization_memberships%rowtype;
  v_request genomeguard.requests%rowtype;
  v_decision_id bigint;
begin
  if p_auth_user_id is null or p_request_id is null
     or p_outcome not in ('approved','denied','needs_more_information')
     or p_reason is null or length(btrim(p_reason)) < 3 or length(btrim(p_reason)) > 2000 then
    raise exception 'invalid_review' using errcode = '22023';
  end if;

  select m.* into v_membership
  from genomeguard.organization_memberships m
  join genomeguard.organizations o on o.id=m.organization_id
  where m.auth_user_id=p_auth_user_id and m.status='active' and o.status='active'
    and m.role in ('reviewer','organization_admin')
  order by m.organization_id
  limit 1;
  if not found then
    raise exception 'active_reviewer_membership_required' using errcode = '42501';
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

  update genomeguard.requests
    set status=case when p_outcome='needs_more_information' then 'needs_more_information'
                    when p_outcome='approved' then 'approved_pending_release'
                    else 'denied' end
    where id=p_request_id;

  insert into genomeguard.api_events(auth_user_id,event_type,request_id,outcome,details)
  values (p_auth_user_id,'research_request_reviewed',p_request_id,p_outcome,
    jsonb_build_object('decision_id',v_decision_id,'reason',btrim(p_reason),
      'organization_id',v_membership.organization_id));

  return jsonb_build_object('request_id',p_request_id,'decision_id',v_decision_id,
    'outcome',p_outcome,'status',case when p_outcome='needs_more_information'
      then 'needs_more_information' when p_outcome='approved'
      then 'approved_pending_release' else 'denied' end,
    'message','Review decision recorded. Approval does not itself release genomic data.');
end;
$$;
revoke all on function public.gg_review_request(uuid,bigint,text,text) from public, anon, authenticated;
grant execute on function public.gg_review_request(uuid,bigint,text,text) to service_role;


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
    and m.role in ('reviewer','organization_admin')
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

comment on table genomeguard.organization_memberships is
  'Authoritative organization and role mapping. Rows must be provisioned by a trusted operator; client role claims are not authoritative.';
comment on table genomeguard.participant_consent_records is
  'Evidence-backed participant consent and withdrawal ledger. Empty means no participant-specific consent has been verified.';
