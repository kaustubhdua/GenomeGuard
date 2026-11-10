-- Protect the signed participant-consent ledger and remove table-wide destructive
-- privileges from the standard runtime role. RLS does not govern TRUNCATE.
ALTER TABLE consent_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE consent_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS consent_events_admin_only ON consent_events;
CREATE POLICY consent_events_admin_only ON consent_events
  FOR ALL
  USING (current_setting('gg.admin_access', true) = 'on')
  WITH CHECK (current_setting('gg.admin_access', true) = 'on');

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'genomeguard_runtime') THEN
    IF EXISTS (
      SELECT 1 FROM pg_roles
      WHERE rolname = 'genomeguard_runtime'
        AND (rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole)
    ) THEN
      RAISE EXCEPTION
        'genomeguard_runtime must be provisioned as NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE before migrations';
    END IF;
    EXECUTE 'REVOKE TRUNCATE ON ALL TABLES IN SCHEMA genomeguard_runtime FROM genomeguard_runtime';
    EXECUTE 'REVOKE TRUNCATE ON ALL TABLES IN SCHEMA genomeguard FROM genomeguard_runtime';
    EXECUTE 'REVOKE CREATE ON SCHEMA genomeguard_runtime FROM genomeguard_runtime';
    EXECUTE 'REVOKE CREATE ON SCHEMA genomeguard FROM genomeguard_runtime';
    EXECUTE 'REVOKE UPDATE, DELETE, TRUNCATE ON consent_events FROM genomeguard_runtime';
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'genomeguard_owner') THEN
      EXECUTE 'REVOKE genomeguard_owner FROM genomeguard_runtime';
      EXECUTE 'ALTER DEFAULT PRIVILEGES FOR ROLE genomeguard_owner IN SCHEMA genomeguard_runtime '
           || 'REVOKE TRUNCATE ON TABLES FROM genomeguard_runtime';
      EXECUTE 'ALTER DEFAULT PRIVILEGES FOR ROLE genomeguard_owner IN SCHEMA genomeguard '
           || 'REVOKE TRUNCATE ON TABLES FROM genomeguard_runtime';
    END IF;
  END IF;
END;
$$;
