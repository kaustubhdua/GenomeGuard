-- Defense in depth for the private GenomeGuard schema.
-- The Python backend uses its server-side PostgreSQL connection; browser roles and
-- Supabase Data API roles must not access genomic or governance tables directly.
-- This migration deliberately creates no client-facing policies.
REVOKE ALL ON SCHEMA genomeguard FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON ALL TABLES IN SCHEMA genomeguard FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA genomeguard FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA genomeguard FROM PUBLIC, anon, authenticated, service_role;

ALTER TABLE genomeguard.schema_migrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE genomeguard.cohort_metadata ENABLE ROW LEVEL SECURITY;
ALTER TABLE genomeguard.donors ENABLE ROW LEVEL SECURITY;
ALTER TABLE genomeguard.genotypes ENABLE ROW LEVEL SECURITY;
ALTER TABLE genomeguard.variants ENABLE ROW LEVEL SECURITY;
ALTER TABLE genomeguard.relationships ENABLE ROW LEVEL SECURITY;
ALTER TABLE genomeguard.requesters ENABLE ROW LEVEL SECURITY;
ALTER TABLE genomeguard.requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE genomeguard.decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE genomeguard.epsilon_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE genomeguard.audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE genomeguard.donor_access ENABLE ROW LEVEL SECURITY;
ALTER TABLE genomeguard.alerts ENABLE ROW LEVEL SECURITY;

-- Ensure future objects created by this migration owner do not receive accidental
-- default grants to browser roles. Server-side backend access remains through the
-- dedicated database connection, not through a browser Supabase client.
ALTER DEFAULT PRIVILEGES IN SCHEMA genomeguard REVOKE ALL ON TABLES FROM PUBLIC, anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA genomeguard REVOKE ALL ON SEQUENCES FROM PUBLIC, anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA genomeguard REVOKE ALL ON FUNCTIONS FROM PUBLIC, anon, authenticated, service_role;
