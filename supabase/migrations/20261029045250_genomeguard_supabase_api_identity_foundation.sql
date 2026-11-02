-- Reconstructed identity foundation migration.
-- The live migration history records this as 20261029045250_genomeguard_supabase_api_identity_foundation.
-- Its exact original source file was absent from the repository. This DDL is reconstructed
-- from the idempotent statements duplicated at the top of the request API migration and
-- verified live column/index state. Review before using this repository for a fresh project.
ALTER TABLE genomeguard.requesters
  ADD COLUMN IF NOT EXISTS auth_user_id uuid;
CREATE UNIQUE INDEX IF NOT EXISTS requesters_auth_user_id_unique
  ON genomeguard.requesters(auth_user_id)
  WHERE auth_user_id IS NOT NULL;
