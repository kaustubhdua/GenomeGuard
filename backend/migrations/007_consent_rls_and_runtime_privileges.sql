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
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gg_app_runtime') THEN
    EXECUTE 'ALTER ROLE gg_app_runtime NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE';
    EXECUTE 'REVOKE TRUNCATE ON ALL TABLES IN SCHEMA genomeguard_runtime FROM gg_app_runtime';
    EXECUTE 'REVOKE TRUNCATE ON ALL TABLES IN SCHEMA genomeguard FROM gg_app_runtime';
    EXECUTE 'REVOKE CREATE ON SCHEMA genomeguard_runtime FROM gg_app_runtime';
    EXECUTE 'REVOKE CREATE ON SCHEMA genomeguard FROM gg_app_runtime';
    EXECUTE 'REVOKE UPDATE, DELETE, TRUNCATE ON consent_events FROM gg_app_runtime';
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'genomeguard_owner') THEN
      EXECUTE 'REVOKE genomeguard_owner FROM gg_app_runtime';
    END IF;
  END IF;
END;
$$;
