-- The legacy requesters table predates Supabase Auth. Add the nullable mapping
-- explicitly in migration history so clean databases match the live schema.
alter table genomeguard.requesters
  add column if not exists auth_user_id uuid;
create unique index if not exists requesters_auth_user_id_unique
  on genomeguard.requesters(auth_user_id)
  where auth_user_id is not null;

-- A revoked or suspended organization member must not retain request-history access.
-- The RPC is called only by the server-side Edge Function after Supabase Auth verifies
-- the bearer token. Membership is rechecked inside the database on every invocation.
create or replace function public.gg_list_my_requests(p_auth_user_id uuid)
returns jsonb
language sql
security definer
set search_path = ''
as $function$
  select coalesce(jsonb_agg(jsonb_build_object(
    'id',q.id,
    'created_at',q.ts,
    'purpose',q.purpose,
    'disease',q.disease,
    'is_commercial',(q.is_commercial = 1),
    'data_level',q.data_level,
    'status',q.status,
    'outcome',d.outcome,
    'needs_human',coalesce(d.needs_human,1) = 1
  ) order by q.id desc),'[]'::jsonb)
  from genomeguard.requests q
  join genomeguard.requesters r on r.id=q.requester_id
  join genomeguard.organizations o
    on o.id=q.organization_id and o.status='active'
  join genomeguard.organization_memberships m
    on m.organization_id=q.organization_id
   and m.auth_user_id=p_auth_user_id
   and m.status='active'
  left join genomeguard.decisions d on d.request_id=q.id
  where p_auth_user_id is not null
    and r.auth_user_id=p_auth_user_id;
$function$;

revoke all on function public.gg_list_my_requests(uuid) from public, anon, authenticated;
grant execute on function public.gg_list_my_requests(uuid) to service_role;

comment on function public.gg_list_my_requests(uuid) is
  'Returns only the authenticated requester own requests while their organization and membership are active; revoked or suspended memberships return an empty list.';
