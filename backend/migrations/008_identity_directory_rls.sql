-- Protect organization membership and requester directory rows at the database layer.
-- OIDC binding lookups set the verified organization context before reading these tables.
ALTER TABLE requesters ENABLE ROW LEVEL SECURITY;
ALTER TABLE requesters FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS requesters_tenant_isolation ON requesters;
CREATE POLICY requesters_tenant_isolation ON requesters
  USING (
    current_setting('gg.admin_access', true) = 'on'
    OR (
      organization_id IS NOT NULL
      AND organization_id = NULLIF(current_setting('gg.organization_id', true), '')
    )
    OR (
      organization_id IS NULL
      AND current_setting('gg.allow_unscoped_demo', true) = 'on'
    )
  )
  WITH CHECK (
    current_setting('gg.admin_access', true) = 'on'
    OR (
      organization_id IS NOT NULL
      AND organization_id = NULLIF(current_setting('gg.organization_id', true), '')
    )
    OR (
      organization_id IS NULL
      AND current_setting('gg.allow_unscoped_demo', true) = 'on'
    )
  );

ALTER TABLE identity_bindings ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity_bindings FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS identity_bindings_tenant_isolation ON identity_bindings;
CREATE POLICY identity_bindings_tenant_isolation ON identity_bindings
  USING (
    current_setting('gg.admin_access', true) = 'on'
    OR organization_id = NULLIF(current_setting('gg.organization_id', true), '')
  )
  WITH CHECK (
    current_setting('gg.admin_access', true) = 'on'
    OR organization_id = NULLIF(current_setting('gg.organization_id', true), '')
  );
