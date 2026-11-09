-- Enforce organization scope in PostgreSQL for requester-owned operational records.
-- The app sets transaction-local gg.organization_id only after validating the OIDC token and
-- resolving an active issuer/subject/organization binding. Admin routes use a separate,
-- application-controlled transaction-local flag after checking the steward credential.
ALTER TABLE requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE requests FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS requests_tenant_isolation ON requests;
CREATE POLICY requests_tenant_isolation ON requests
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

ALTER TABLE decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE decisions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS decisions_tenant_isolation ON decisions;
CREATE POLICY decisions_tenant_isolation ON decisions
  USING (
    current_setting('gg.admin_access', true) = 'on'
    OR EXISTS (
      SELECT 1 FROM requests r
      WHERE r.id = decisions.request_id
        AND (
          r.organization_id = NULLIF(current_setting('gg.organization_id', true), '')
          OR (r.organization_id IS NULL
              AND current_setting('gg.allow_unscoped_demo', true) = 'on')
        )
    )
  )
  WITH CHECK (
    current_setting('gg.admin_access', true) = 'on'
    OR EXISTS (
      SELECT 1 FROM requests r
      WHERE r.id = decisions.request_id
        AND (
          r.organization_id = NULLIF(current_setting('gg.organization_id', true), '')
          OR (r.organization_id IS NULL
              AND current_setting('gg.allow_unscoped_demo', true) = 'on')
        )
    )
  );

ALTER TABLE epsilon_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE epsilon_ledger FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS epsilon_ledger_tenant_isolation ON epsilon_ledger;
CREATE POLICY epsilon_ledger_tenant_isolation ON epsilon_ledger
  USING (
    current_setting('gg.admin_access', true) = 'on'
    OR EXISTS (
      SELECT 1 FROM requesters r WHERE r.id = epsilon_ledger.requester_id
        AND (
          r.organization_id = NULLIF(current_setting('gg.organization_id', true), '')
          OR (r.organization_id IS NULL
              AND current_setting('gg.allow_unscoped_demo', true) = 'on')
        )
    )
  )
  WITH CHECK (
    current_setting('gg.admin_access', true) = 'on'
    OR EXISTS (
      SELECT 1 FROM requesters r WHERE r.id = epsilon_ledger.requester_id
        AND (
          r.organization_id = NULLIF(current_setting('gg.organization_id', true), '')
          OR (r.organization_id IS NULL
              AND current_setting('gg.allow_unscoped_demo', true) = 'on')
        )
    )
  );

ALTER TABLE alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS alerts_tenant_isolation ON alerts;
CREATE POLICY alerts_tenant_isolation ON alerts
  USING (
    current_setting('gg.admin_access', true) = 'on'
    OR EXISTS (
      SELECT 1 FROM requesters r WHERE r.id = alerts.requester_id
        AND (
          r.organization_id = NULLIF(current_setting('gg.organization_id', true), '')
          OR (r.organization_id IS NULL
              AND current_setting('gg.allow_unscoped_demo', true) = 'on')
        )
    )
  )
  WITH CHECK (
    current_setting('gg.admin_access', true) = 'on'
    OR EXISTS (
      SELECT 1 FROM requesters r WHERE r.id = alerts.requester_id
        AND (
          r.organization_id = NULLIF(current_setting('gg.organization_id', true), '')
          OR (r.organization_id IS NULL
              AND current_setting('gg.allow_unscoped_demo', true) = 'on')
        )
    )
  );

