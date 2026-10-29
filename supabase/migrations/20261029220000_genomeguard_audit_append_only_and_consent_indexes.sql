-- Operational hardening for GenomeGuard only. Does not alter BharatSim objects.
-- This migration is intentionally ordered after the organization/consent, normalized genotype,
-- and request-detail tables because it indexes participant_consent_records.
CREATE INDEX IF NOT EXISTS participant_consent_dataset_key_idx
  ON genomeguard.participant_consent_records (dataset_key);
CREATE INDEX IF NOT EXISTS participant_consent_organization_id_idx
  ON genomeguard.participant_consent_records (organization_id);

-- Audit history is append-only for the application role. Tamper-evidence still requires
-- an independently controlled external anchor; this trigger is not a substitute for one.
CREATE OR REPLACE FUNCTION genomeguard.reject_audit_log_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, genomeguard
AS $function$
BEGIN
  RAISE EXCEPTION 'GenomeGuard audit_log is append-only; UPDATE and DELETE are prohibited'
    USING ERRCODE = '55000';
END;
$function$;

REVOKE ALL ON FUNCTION genomeguard.reject_audit_log_mutation() FROM PUBLIC, anon, authenticated, service_role;

DROP TRIGGER IF EXISTS genomeguard_audit_log_append_only ON genomeguard.audit_log;
CREATE TRIGGER genomeguard_audit_log_append_only
  BEFORE UPDATE OR DELETE ON genomeguard.audit_log
  FOR EACH ROW EXECUTE FUNCTION genomeguard.reject_audit_log_mutation();

COMMENT ON FUNCTION genomeguard.reject_audit_log_mutation() IS
  'Rejects ordinary UPDATE/DELETE on GenomeGuard audit history. Does not provide external immutable anchoring.';
