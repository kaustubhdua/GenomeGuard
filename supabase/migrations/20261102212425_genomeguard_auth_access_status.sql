-- Read-only identity and organization-membership summary for the signed-in user.
-- The Edge Function verifies the bearer token before supplying p_auth_user_id.
CREATE OR REPLACE FUNCTION public.gg_get_my_access_status(
  p_auth_user_id uuid
) RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  v_memberships jsonb;
  v_active_count integer;
  v_total_count integer;
BEGIN
  IF p_auth_user_id IS NULL THEN
    RAISE EXCEPTION 'invalid_identity' USING ERRCODE = '22023';
  END IF;

  SELECT
    coalesce(jsonb_agg(jsonb_build_object(
      'organization_id', m.organization_id,
      'organization', o.display_name,
      'organization_slug', o.slug,
      'organization_status', o.status,
      'role', m.role,
      'status', m.status,
      'activated_at', m.activated_at,
      'revoked_at', m.revoked_at
    ) ORDER BY o.display_name, m.created_at), '[]'::jsonb),
    count(*) FILTER (WHERE m.status = 'active' AND o.status = 'active')::integer,
    count(*)::integer
  INTO v_memberships, v_active_count, v_total_count
  FROM genomeguard.organization_memberships m
  JOIN genomeguard.organizations o ON o.id = m.organization_id
  WHERE m.auth_user_id = p_auth_user_id;

  RETURN jsonb_build_object(
    'user_id', p_auth_user_id,
    'memberships', v_memberships,
    'active_membership_count', v_active_count,
    'membership_count', v_total_count,
    'access_status', CASE
      WHEN v_active_count = 1 THEN 'active'
      WHEN v_active_count > 1 THEN 'ambiguous_memberships'
      WHEN v_total_count > 0 THEN 'pending_or_inactive'
      ELSE 'no_membership'
    END
  );
END;
$$;

REVOKE ALL ON FUNCTION public.gg_get_my_access_status(uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.gg_get_my_access_status(uuid)
  TO service_role;
