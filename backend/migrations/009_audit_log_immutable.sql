-- Make the audit chain append-only even for the application runtime principal.
CREATE OR REPLACE FUNCTION genomeguard.reject_audit_log_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $gg_audit$
BEGIN
  RAISE EXCEPTION 'audit_log is append-only' USING ERRCODE = '55000';
END;
$gg_audit$;

DROP TRIGGER IF EXISTS audit_log_immutable ON audit_log;
CREATE TRIGGER audit_log_immutable
BEFORE UPDATE OR DELETE ON audit_log
FOR EACH ROW EXECUTE FUNCTION genomeguard.reject_audit_log_mutation();

DO $gg_audit$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'genomeguard_runtime') THEN
    EXECUTE 'REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM genomeguard_runtime';
    EXECUTE 'REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON schema_migrations FROM genomeguard_runtime';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'genomeguard_app_runtime') THEN
    EXECUTE 'REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM genomeguard_app_runtime';
    EXECUTE 'REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON schema_migrations FROM genomeguard_app_runtime';
  END IF;
END;
$$;
