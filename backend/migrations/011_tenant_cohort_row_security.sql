-- Give institution-owned cohort rows explicit organization boundaries while
-- keeping only the public/synthetic reference cohort globally readable.
-- Existing rows receive NULL organization_id and remain shared public/demo data.
-- New rows inherit the current transaction's organization when one is set.
DO $gg_cohort_columns$
DECLARE
  table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'donors', 'genotypes', 'variants', 'relationships',
    'cohort_metadata', 'donor_access'
  ]
  LOOP
    EXECUTE format(
      'ALTER TABLE genomeguard_runtime.%I ADD COLUMN IF NOT EXISTS organization_id text '
      || 'DEFAULT NULLIF(current_setting(''gg.organization_id'', true), '''')',
      table_name
    );
    EXECUTE format(
      'CREATE INDEX IF NOT EXISTS %I ON genomeguard_runtime.%I (organization_id)',
      table_name || '_organization_idx', table_name
    );
  END LOOP;
END;
$gg_cohort_columns$;

-- A donor's organization is part of the referential identity for every child row.
DO $gg_cohort_constraints$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname='donors_id_organization_unique'
      AND conrelid='genomeguard_runtime.donors'::regclass
  ) THEN
    ALTER TABLE genomeguard_runtime.donors
      ADD CONSTRAINT donors_id_organization_unique UNIQUE (id, organization_id);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname='genotypes_donor_organization_fk'
      AND conrelid='genomeguard_runtime.genotypes'::regclass
  ) THEN
    ALTER TABLE genomeguard_runtime.genotypes
      ADD CONSTRAINT genotypes_donor_organization_fk
      FOREIGN KEY (donor_id, organization_id)
      REFERENCES genomeguard_runtime.donors(id, organization_id);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname='relationships_donor_a_organization_fk'
      AND conrelid='genomeguard_runtime.relationships'::regclass
  ) THEN
    ALTER TABLE genomeguard_runtime.relationships
      ADD CONSTRAINT relationships_donor_a_organization_fk
      FOREIGN KEY (donor_a, organization_id)
      REFERENCES genomeguard_runtime.donors(id, organization_id);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname='relationships_donor_b_organization_fk'
      AND conrelid='genomeguard_runtime.relationships'::regclass
  ) THEN
    ALTER TABLE genomeguard_runtime.relationships
      ADD CONSTRAINT relationships_donor_b_organization_fk
      FOREIGN KEY (donor_b, organization_id)
      REFERENCES genomeguard_runtime.donors(id, organization_id);
  END IF;

END;
$gg_cohort_constraints$;

-- RLS policy helpers: public rows (NULL organization_id) are the synthetic/public
-- fixture only; tenant rows are visible only to their tenant and explicit admins.
ALTER TABLE genomeguard_runtime.donors ENABLE ROW LEVEL SECURITY;
ALTER TABLE genomeguard_runtime.donors FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS donors_shared_read ON genomeguard_runtime.donors;
DROP POLICY IF EXISTS donors_scoped_read ON genomeguard_runtime.donors;
CREATE POLICY donors_scoped_read ON genomeguard_runtime.donors
  FOR SELECT USING (
    organization_id IS NULL
    OR current_setting('gg.admin_access', true) = 'on'
    OR organization_id = NULLIF(current_setting('gg.organization_id', true), '')
    OR current_user = 'genomeguard_owner'
  );
DROP POLICY IF EXISTS donors_admin_update ON genomeguard_runtime.donors;
CREATE POLICY donors_admin_update ON genomeguard_runtime.donors
  FOR UPDATE
  USING (
    current_setting('gg.admin_access', true) = 'on'
    OR current_user = 'genomeguard_owner'
  )
  WITH CHECK (
    current_setting('gg.admin_access', true) = 'on'
    OR current_user = 'genomeguard_owner'
  );
DROP POLICY IF EXISTS donors_admin_insert ON genomeguard_runtime.donors;
CREATE POLICY donors_admin_insert ON genomeguard_runtime.donors
  FOR INSERT WITH CHECK (
    current_setting('gg.admin_access', true) = 'on'
    OR current_user = 'genomeguard_owner'
    OR organization_id = NULLIF(current_setting('gg.organization_id', true), '')
    OR (organization_id IS NULL AND current_setting('gg.allow_unscoped_demo', true) = 'on')
  );
DROP POLICY IF EXISTS donors_admin_delete ON genomeguard_runtime.donors;
CREATE POLICY donors_admin_delete ON genomeguard_runtime.donors
  FOR DELETE USING (
    current_setting('gg.admin_access', true) = 'on'
    OR current_user = 'genomeguard_owner'
  );

DO $gg_tenant_cohort_rls$
DECLARE
  table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'genotypes', 'variants', 'relationships', 'cohort_metadata'
  ]
  LOOP
    EXECUTE format('ALTER TABLE genomeguard_runtime.%I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE genomeguard_runtime.%I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('DROP POLICY IF EXISTS %I ON genomeguard_runtime.%I',
                   table_name || '_organization_read', table_name);
    EXECUTE format(
      'CREATE POLICY %I ON genomeguard_runtime.%I FOR SELECT USING ('
      || 'organization_id IS NULL '
      || 'OR current_setting(''gg.admin_access'', true) = ''on'' '
      || 'OR organization_id = NULLIF(current_setting(''gg.organization_id'', true), '''') '
      || 'OR current_user = ''genomeguard_owner'')',
      table_name || '_organization_read', table_name
    );
    EXECUTE format('DROP POLICY IF EXISTS %I ON genomeguard_runtime.%I',
                   table_name || '_organization_insert', table_name);
    EXECUTE format(
      'CREATE POLICY %I ON genomeguard_runtime.%I FOR INSERT WITH CHECK ('
      || 'current_setting(''gg.admin_access'', true) = ''on'' '
      || 'OR current_user = ''genomeguard_owner'' '
      || 'OR organization_id = NULLIF(current_setting(''gg.organization_id'', true), '''') '
      || 'OR (organization_id IS NULL AND current_setting(''gg.allow_unscoped_demo'', true) = ''on''))',
      table_name || '_organization_insert', table_name
    );
    EXECUTE format('DROP POLICY IF EXISTS %I ON genomeguard_runtime.%I',
                   table_name || '_organization_update', table_name);
    EXECUTE format(
      'CREATE POLICY %I ON genomeguard_runtime.%I FOR UPDATE USING ('
      || 'current_setting(''gg.admin_access'', true) = ''on'' '
      || 'OR current_user = ''genomeguard_owner'' '
      || 'OR organization_id = NULLIF(current_setting(''gg.organization_id'', true), '''')) '
      || 'WITH CHECK (current_setting(''gg.admin_access'', true) = ''on'' '
      || 'OR current_user = ''genomeguard_owner'' '
      || 'OR organization_id = NULLIF(current_setting(''gg.organization_id'', true), ''''))',
      table_name || '_organization_update', table_name
    );
    EXECUTE format('DROP POLICY IF EXISTS %I ON genomeguard_runtime.%I',
                   table_name || '_organization_delete', table_name);
    EXECUTE format(
      'CREATE POLICY %I ON genomeguard_runtime.%I FOR DELETE USING ('
      || 'current_setting(''gg.admin_access'', true) = ''on'' '
      || 'OR current_user = ''genomeguard_owner'' '
      || 'OR organization_id = NULLIF(current_setting(''gg.organization_id'', true), ''''))',
      table_name || '_organization_delete', table_name
    );
  END LOOP;
END;
$gg_tenant_cohort_rls$;

ALTER TABLE genomeguard_runtime.donor_access ENABLE ROW LEVEL SECURITY;
ALTER TABLE genomeguard_runtime.donor_access FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS donor_access_scoped_insert ON genomeguard_runtime.donor_access;
CREATE POLICY donor_access_scoped_insert ON genomeguard_runtime.donor_access
  FOR INSERT WITH CHECK (
    current_setting('gg.admin_access', true) = 'on'
    OR current_user = 'genomeguard_owner'
    OR organization_id = NULLIF(current_setting('gg.organization_id', true), '')
    OR (organization_id IS NULL AND current_setting('gg.allow_unscoped_demo', true) = 'on')
  );
DROP POLICY IF EXISTS donor_access_admin_read ON genomeguard_runtime.donor_access;
CREATE POLICY donor_access_admin_read ON genomeguard_runtime.donor_access
  FOR SELECT USING (
    current_setting('gg.admin_access', true) = 'on'
    OR organization_id = NULLIF(current_setting('gg.organization_id', true), '')
    OR current_user = 'genomeguard_owner'
  );
DROP POLICY IF EXISTS donor_access_admin_update ON genomeguard_runtime.donor_access;
CREATE POLICY donor_access_admin_update ON genomeguard_runtime.donor_access
  FOR UPDATE USING (
    current_setting('gg.admin_access', true) = 'on'
    OR current_user = 'genomeguard_owner'
  )
  WITH CHECK (
    current_setting('gg.admin_access', true) = 'on'
    OR current_user = 'genomeguard_owner'
  );
DROP POLICY IF EXISTS donor_access_admin_delete ON genomeguard_runtime.donor_access;
CREATE POLICY donor_access_admin_delete ON genomeguard_runtime.donor_access
  FOR DELETE USING (
    current_setting('gg.admin_access', true) = 'on'
    OR current_user = 'genomeguard_owner'
  );


-- Access-event organization_id is the requesting tenant, not necessarily the
-- ownership of a shared public/synthetic donor. A tenant may query a public donor;
-- it must never log or read another institution's private donor.
DO $gg_donor_access_fk$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname='donor_access_donor_organization_fk'
      AND conrelid='genomeguard_runtime.donor_access'::regclass
  ) THEN
    ALTER TABLE genomeguard_runtime.donor_access
      DROP CONSTRAINT donor_access_donor_organization_fk;
  END IF;
END;
$gg_donor_access_fk$;

CREATE OR REPLACE FUNCTION genomeguard_runtime.enforce_donor_access_organization()
RETURNS trigger
LANGUAGE plpgsql
AS $gg_donor_access_org$
DECLARE
  donor_organization text;
BEGIN
  SELECT organization_id INTO donor_organization
  FROM genomeguard_runtime.donors WHERE id=NEW.donor_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'donor is not visible in the active organization scope';
  END IF;
  IF donor_organization IS NOT NULL
     AND donor_organization IS DISTINCT FROM NEW.organization_id THEN
    RAISE EXCEPTION 'donor-access event organization does not match donor owner';
  END IF;
  RETURN NEW;
END;
$gg_donor_access_org$;

DROP TRIGGER IF EXISTS donor_access_organization_guard ON genomeguard_runtime.donor_access;
CREATE TRIGGER donor_access_organization_guard
  BEFORE INSERT OR UPDATE OF donor_id, organization_id
  ON genomeguard_runtime.donor_access
  FOR EACH ROW EXECUTE FUNCTION genomeguard_runtime.enforce_donor_access_organization();


-- The web role can read shared/public and tenant-scoped cohort rows, but cannot
-- ingest, rewrite, or delete genotype, variant, relationship, or metadata rows.
DO $gg_runtime_cohort_grants$
DECLARE
  runtime_role text;
BEGIN
  FOREACH runtime_role IN ARRAY ARRAY['genomeguard_runtime', 'genomeguard_app_runtime']
  LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=runtime_role) THEN
      EXECUTE format(
        'REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE '
        || 'genomeguard_runtime.genotypes, genomeguard_runtime.variants, '
        || 'genomeguard_runtime.relationships, genomeguard_runtime.cohort_metadata '
        || 'FROM %I', runtime_role
      );
      EXECUTE format(
        'GRANT SELECT ON TABLE genomeguard_runtime.genotypes, genomeguard_runtime.variants, '
        || 'genomeguard_runtime.relationships, genomeguard_runtime.cohort_metadata TO %I',
        runtime_role
      );
    END IF;
  END LOOP;
END;
$gg_runtime_cohort_grants$;
