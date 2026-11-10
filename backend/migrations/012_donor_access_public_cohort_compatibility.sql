-- Correct donor-access tenant binding: the event belongs to the requesting
-- organization, while the donor may be a shared public/synthetic row. Keep the
-- simple donor FK and enforce tenant-owned donor matching with a row trigger.
ALTER TABLE genomeguard_runtime.donor_access
  DROP CONSTRAINT IF EXISTS donor_access_donor_organization_fk;

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
