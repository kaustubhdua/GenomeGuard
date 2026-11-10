-- Restrict application writes to the operations used by the live API.
-- Cohort loading/import is an operator task and must not run through the web role.
ALTER TABLE donors ENABLE ROW LEVEL SECURITY;
ALTER TABLE donors FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS donors_shared_read ON donors;
CREATE POLICY donors_shared_read ON donors
  FOR SELECT USING (true);
DROP POLICY IF EXISTS donors_admin_update ON donors;
CREATE POLICY donors_admin_update ON donors
  FOR UPDATE
  USING (current_setting('gg.admin_access', true) = 'on')
  WITH CHECK (current_setting('gg.admin_access', true) = 'on');

-- Donor-access records are written inside an authenticated tenant/demo transaction.
-- Reading the cross-request access history is reserved for authenticated admins.
ALTER TABLE donor_access ENABLE ROW LEVEL SECURITY;
ALTER TABLE donor_access FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS donor_access_scoped_insert ON donor_access;
CREATE POLICY donor_access_scoped_insert ON donor_access
  FOR INSERT
  WITH CHECK (
    current_setting('gg.admin_access', true) = 'on'
    OR NULLIF(current_setting('gg.organization_id', true), '') IS NOT NULL
    OR current_setting('gg.allow_unscoped_demo', true) = 'on'
  );
DROP POLICY IF EXISTS donor_access_admin_read ON donor_access;
CREATE POLICY donor_access_admin_read ON donor_access
  FOR SELECT USING (current_setting('gg.admin_access', true) = 'on');

DO $gg_cohort_privileges$
DECLARE
  runtime_role text;
BEGIN
  FOREACH runtime_role IN ARRAY ARRAY['genomeguard_runtime', 'genomeguard_app_runtime']
  LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = runtime_role) THEN
      -- Start from no table writes and grant only the service's documented DML.
      EXECUTE format(
        'REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA genomeguard_runtime FROM %I',
        runtime_role
      );
      EXECUTE format(
        'GRANT SELECT ON ALL TABLES IN SCHEMA genomeguard_runtime TO %I',
        runtime_role
      );
      EXECUTE format(
        'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA genomeguard_runtime TO %I',
        runtime_role
      );
      EXECUTE format(
        'GRANT INSERT, UPDATE ON TABLE genomeguard_runtime.requesters, genomeguard_runtime.requests, genomeguard_runtime.decisions, genomeguard_runtime.epsilon_ledger, genomeguard_runtime.identity_bindings, genomeguard_runtime.donors TO %I',
        runtime_role
      );
      EXECUTE format(
        'GRANT INSERT ON TABLE genomeguard_runtime.alerts, genomeguard_runtime.donor_access, genomeguard_runtime.audit_log, genomeguard_runtime.consent_events TO %I',
        runtime_role
      );
      EXECUTE format(
        'REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE genomeguard_runtime.schema_migrations FROM %I',
        runtime_role
      );
      EXECUTE format(
        'REVOKE UPDATE, DELETE, TRUNCATE ON TABLE genomeguard_runtime.audit_log, genomeguard_runtime.consent_events FROM %I',
        runtime_role
      );

      -- The normalized public-reference schema is read-only to application roles.
      EXECUTE format(
        'REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA genomeguard FROM %I',
        runtime_role
      );
      EXECUTE format(
        'GRANT SELECT ON ALL TABLES IN SCHEMA genomeguard TO %I',
        runtime_role
      );

      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'genomeguard_owner') THEN
        EXECUTE format(
          'ALTER DEFAULT PRIVILEGES FOR ROLE genomeguard_owner IN SCHEMA genomeguard_runtime REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLES FROM %I',
          runtime_role
        );
        EXECUTE format(
          'ALTER DEFAULT PRIVILEGES FOR ROLE genomeguard_owner IN SCHEMA genomeguard_runtime GRANT SELECT ON TABLES TO %I',
          runtime_role
        );
        EXECUTE format(
          'ALTER DEFAULT PRIVILEGES FOR ROLE genomeguard_owner IN SCHEMA genomeguard_runtime GRANT USAGE, SELECT ON SEQUENCES TO %I',
          runtime_role
        );
        EXECUTE format(
          'ALTER DEFAULT PRIVILEGES FOR ROLE genomeguard_owner IN SCHEMA genomeguard REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLES FROM %I',
          runtime_role
        );
        EXECUTE format(
          'ALTER DEFAULT PRIVILEGES FOR ROLE genomeguard_owner IN SCHEMA genomeguard GRANT SELECT ON TABLES TO %I',
          runtime_role
        );
      END IF;
    END IF;
  END LOOP;
END;
$gg_cohort_privileges$;
