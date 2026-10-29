-- Harden validation at the database boundary as well as in the Edge Function.
-- This migration deliberately changes only GenomeGuard objects in the shared project.
CREATE OR REPLACE FUNCTION public.gg_submit_request(
  p_auth_user_id uuid, p_name text, p_institution text, p_purpose text,
  p_disease text, p_is_commercial boolean, p_data_level text,
  p_cohort_filter jsonb, p_variant_filter jsonb
) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
DECLARE v_requester_id bigint; v_request_id bigint;
BEGIN
  IF p_auth_user_id IS NULL
     OR p_purpose IS NULL OR length(btrim(p_purpose)) < 3 OR length(btrim(p_purpose)) > 500
     OR p_data_level IS NULL OR p_data_level NOT IN ('aggregate', 'frequency', 'variant', 'individual')
     OR p_name IS NULL OR length(btrim(p_name)) < 2 OR length(btrim(p_name)) > 120
     OR p_institution IS NULL OR length(btrim(p_institution)) < 2 OR length(btrim(p_institution)) > 200
     OR p_is_commercial IS NULL
     OR (p_disease IS NOT NULL AND length(btrim(p_disease)) > 200)
     OR jsonb_typeof(coalesce(p_cohort_filter, '{}'::jsonb)) <> 'object'
     OR jsonb_typeof(coalesce(p_variant_filter, '{}'::jsonb)) <> 'object' THEN
    RAISE EXCEPTION 'invalid_request' USING ERRCODE = '22023';
  END IF;

  INSERT INTO genomeguard.requesters(auth_user_id,name,role,credential_level,institution,created_at)
  VALUES (p_auth_user_id,btrim(p_name),'researcher','registered',btrim(p_institution),now()::text)
  ON CONFLICT (auth_user_id) WHERE auth_user_id IS NOT NULL
  DO UPDATE SET name=EXCLUDED.name,institution=EXCLUDED.institution
  RETURNING id INTO v_requester_id;

  INSERT INTO genomeguard.requests(
    requester_id,ts,purpose,disease,is_commercial,data_level,
    cohort_filter_json,variant_filter_json,status
  ) VALUES (
    v_requester_id,now()::text,btrim(p_purpose),nullif(btrim(coalesce(p_disease,'')),''),
    CASE WHEN p_is_commercial THEN 1 ELSE 0 END,p_data_level,
    coalesce(p_cohort_filter,'{}'::jsonb)::text,coalesce(p_variant_filter,'{}'::jsonb)::text,
    'pending_review'
  ) RETURNING id INTO v_request_id;

  INSERT INTO genomeguard.api_events(auth_user_id,event_type,request_id,outcome,details)
  VALUES (p_auth_user_id,'research_request_submitted',v_request_id,'pending_review',
    jsonb_build_object('data_level',p_data_level,'commercial',p_is_commercial));

  RETURN jsonb_build_object('id',v_request_id,'status','pending_review',
    'message','Request stored for steward review. No data access has been granted.');
END;
$$;

REVOKE ALL ON FUNCTION public.gg_submit_request(uuid,text,text,text,text,boolean,text,jsonb,jsonb)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.gg_submit_request(uuid,text,text,text,text,boolean,text,jsonb,jsonb)
  TO service_role;
