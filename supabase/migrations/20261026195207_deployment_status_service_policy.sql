-- Explicitly scope reads to the server-side service role; browser roles have no grants.
CREATE POLICY genomeguard_deployment_status_service_read
  ON public.genomeguard_deployment_status
  FOR SELECT
  TO service_role
  USING (true);
