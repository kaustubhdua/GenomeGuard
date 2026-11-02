-- Authorized, organization-scoped steward queue for the Supabase request workflow.
-- The caller identity is verified by the Edge Function via Supabase Auth; this RPC is
-- service_role-only and independently resolves active membership and organization.
CREATE OR REPLACE FUNCTION public.gg_list_review_queue(
  p_auth_user_id uuid,
  p_limit integer DEFAULT 50,
  p_offset integer DEFAULT 0
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  v_membership genomeguard.organization_memberships%rowtype;
  v_membership_count integer;
  v_requests jsonb;
  v_total bigint;
BEGIN
  IF p_auth_user_id IS NULL
     OR p_limit IS NULL OR p_limit < 1 OR p_limit > 100
     OR p_offset IS NULL OR p_offset < 0 OR p_offset > 100000 THEN
    RAISE EXCEPTION 'invalid_review_queue_query' USING ERRCODE = '22023';
  END IF;

  SELECT count(*) INTO v_membership_count
  FROM genomeguard.organization_memberships m
  JOIN genomeguard.organizations o ON o.id = m.organization_id
  WHERE m.auth_user_id = p_auth_user_id
    AND m.status = 'active' AND o.status = 'active'
    AND m.role IN ('reviewer', 'organization_admin');

  IF v_membership_count = 0 THEN
    RAISE EXCEPTION 'active_reviewer_membership_required' USING ERRCODE = '42501';
  ELSIF v_membership_count > 1 THEN
    RAISE EXCEPTION 'explicit_organization_selection_required' USING ERRCODE = '22023';
  END IF;

  SELECT m.* INTO STRICT v_membership
  FROM genomeguard.organization_memberships m
  JOIN genomeguard.organizations o ON o.id = m.organization_id
  WHERE m.auth_user_id = p_auth_user_id
    AND m.status = 'active' AND o.status = 'active'
    AND m.role IN ('reviewer', 'organization_admin');

  SELECT count(*) INTO v_total
  FROM genomeguard.requests q
  WHERE q.organization_id = v_membership.organization_id
    AND q.status IN ('pending_review', 'needs_more_information');

  SELECT coalesce(jsonb_agg(item ORDER BY request_id DESC), '[]'::jsonb)
  INTO v_requests
  FROM (
    SELECT
      q.id AS request_id,
      jsonb_build_object(
        'id', q.id,
        'ts', q.ts,
        'status', q.status,
        'requester', r.name,
        'institution', r.institution,
        'request', jsonb_build_object(
          'purpose', q.purpose,
          'disease', q.disease,
          'is_commercial', q.is_commercial = 1,
          'data_level', q.data_level
        ),
        'outcome', coalesce(d.outcome, 'pending'),
        'needs_human', coalesce(d.needs_human, 1) = 1
      ) AS item
    FROM genomeguard.requests q
    JOIN genomeguard.requesters r ON r.id = q.requester_id
    LEFT JOIN genomeguard.decisions d ON d.request_id = q.id
    WHERE q.organization_id = v_membership.organization_id
      AND q.status IN ('pending_review', 'needs_more_information')
    ORDER BY q.id DESC
    LIMIT p_limit OFFSET p_offset
  ) page;

  RETURN jsonb_build_object(
    'requests', v_requests,
    'total_count', v_total,
    'limit', p_limit,
    'offset', p_offset
  );
END;
$$;

REVOKE ALL ON FUNCTION public.gg_list_review_queue(uuid, integer, integer)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.gg_list_review_queue(uuid, integer, integer)
  TO service_role;
