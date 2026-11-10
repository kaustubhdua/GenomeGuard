-- Protect the signed participant-consent ledger and remove table-wide destructive
-- privileges from the standard runtime role. RLS does not govern TRUNCATE.
ALTER TABLE consent_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE consent_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS consent_events_admin_only ON consent_events;
CREATE POLICY consent_events_admin_only ON consent_events
  FOR ALL
  USING (current_setting('gg.admin_access', true) = 'on')
  WITH CHECK (current_setting('gg.admin_access', true) = 'on');

DO $gg_migration$
DECLARE
  object_row RECORD;
BEGIN
  -- Move schema/object ownership to the migration principal before revoking CREATE
  -- from the application principal. Existing explicit DML grants are preserved.
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'genomeguard_owner')
     AND EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'genomeguard_runtime') THEN
    ALTER SCHEMA genomeguard_runtime OWNER TO genomeguard_owner;
    FOR object_row IN
      SELECT c.relkind, c.relname
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE n.nspname = 'genomeguard_runtime'
        AND c.relowner = (SELECT oid FROM pg_roles WHERE rolname = 'genomeguard_runtime')
        AND c.relkind IN ('r', 'p', 'S', 'v', 'm', 'f')
        AND (
          c.relkind <> 'S'
          OR NOT EXISTS (
            SELECT 1 FROM pg_depend d
            WHERE d.classid = 'pg_class'::regclass
              AND d.objid = c.oid
              AND d.refclassid = 'pg_class'::regclass
              AND d.deptype IN ('a', 'i')
          )
        )
    LOOP
      IF object_row.relkind = 'S' THEN
        EXECUTE format('ALTER SEQUENCE genomeguard_runtime.%I OWNER TO genomeguard_owner', object_row.relname);
      ELSIF object_row.relkind = 'v' THEN
        EXECUTE format('ALTER VIEW genomeguard_runtime.%I OWNER TO genomeguard_owner', object_row.relname);
      ELSIF object_row.relkind = 'm' THEN
        EXECUTE format('ALTER MATERIALIZED VIEW genomeguard_runtime.%I OWNER TO genomeguard_owner', object_row.relname);
      ELSIF object_row.relkind = 'f' THEN
        EXECUTE format('ALTER FOREIGN TABLE genomeguard_runtime.%I OWNER TO genomeguard_owner', object_row.relname);
      ELSE
        EXECUTE format('ALTER TABLE genomeguard_runtime.%I OWNER TO genomeguard_owner', object_row.relname);
      END IF;
    END LOOP;
    FOR object_row IN
      SELECT p.oid::regprocedure AS signature
      FROM pg_proc p
      JOIN pg_namespace n ON n.oid = p.pronamespace
      WHERE n.nspname = 'genomeguard_runtime'
        AND p.proowner = (SELECT oid FROM pg_roles WHERE rolname = 'genomeguard_runtime')
    LOOP
      EXECUTE format('ALTER FUNCTION %s OWNER TO genomeguard_owner', object_row.signature);
    END LOOP;
  END IF;

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
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'genomeguard_app_runtime') THEN
      IF EXISTS (
        SELECT 1 FROM pg_roles
        WHERE rolname = 'genomeguard_app_runtime'
          AND (rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole)
      ) THEN
        RAISE EXCEPTION
          'genomeguard_app_runtime must be provisioned as NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE before migrations';
      END IF;
      IF pg_has_role('genomeguard_app_runtime', 'genomeguard_owner', 'MEMBER') THEN
        RAISE EXCEPTION
          'genomeguard_app_runtime must not inherit genomeguard_owner privileges';
      END IF;
      EXECUTE 'REVOKE TRUNCATE ON ALL TABLES IN SCHEMA genomeguard_runtime FROM genomeguard_app_runtime';
      EXECUTE 'REVOKE TRUNCATE ON ALL TABLES IN SCHEMA genomeguard FROM genomeguard_app_runtime';
      EXECUTE 'REVOKE CREATE ON SCHEMA genomeguard_runtime FROM genomeguard_app_runtime';
      EXECUTE 'REVOKE CREATE ON SCHEMA genomeguard FROM genomeguard_app_runtime';
      EXECUTE 'REVOKE UPDATE, DELETE, TRUNCATE ON consent_events FROM genomeguard_app_runtime';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'genomeguard_owner') THEN
      IF pg_has_role('genomeguard_runtime', 'genomeguard_owner', 'MEMBER') THEN
        RAISE EXCEPTION
          'genomeguard_runtime must not inherit genomeguard_owner privileges; remove provider role membership before migrations';
      END IF;
      EXECUTE 'ALTER DEFAULT PRIVILEGES FOR ROLE genomeguard_owner IN SCHEMA genomeguard_runtime '
           || 'REVOKE TRUNCATE ON TABLES FROM genomeguard_runtime';
      EXECUTE 'ALTER DEFAULT PRIVILEGES FOR ROLE genomeguard_owner IN SCHEMA genomeguard '
           || 'REVOKE TRUNCATE ON TABLES FROM genomeguard_runtime';
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'genomeguard_app_runtime') THEN
        EXECUTE 'ALTER DEFAULT PRIVILEGES FOR ROLE genomeguard_owner IN SCHEMA genomeguard_runtime '
             || 'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO genomeguard_app_runtime';
        EXECUTE 'ALTER DEFAULT PRIVILEGES FOR ROLE genomeguard_owner IN SCHEMA genomeguard_runtime '
             || 'GRANT USAGE, SELECT ON SEQUENCES TO genomeguard_app_runtime';
        EXECUTE 'ALTER DEFAULT PRIVILEGES FOR ROLE genomeguard_owner IN SCHEMA genomeguard_runtime '
             || 'REVOKE TRUNCATE ON TABLES FROM genomeguard_app_runtime';
        EXECUTE 'ALTER DEFAULT PRIVILEGES FOR ROLE genomeguard_owner IN SCHEMA genomeguard '
             || 'GRANT SELECT ON TABLES TO genomeguard_app_runtime';
        EXECUTE 'ALTER DEFAULT PRIVILEGES FOR ROLE genomeguard_owner IN SCHEMA genomeguard '
             || 'REVOKE TRUNCATE ON TABLES FROM genomeguard_app_runtime';
      END IF;
    END IF;
  END IF;
END;
$gg_migration$;
