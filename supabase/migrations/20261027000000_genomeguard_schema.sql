-- GenomeGuard's existing PostgreSQL storage contract, provisioned in the private schema.
-- This preserves the table names and schema_migrations version expected by backend/app/postgres_store.py.
CREATE SCHEMA IF NOT EXISTS genomeguard;
REVOKE ALL ON SCHEMA genomeguard FROM PUBLIC, anon, authenticated, service_role;
SET search_path TO genomeguard, public;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cohort_metadata (
  id INTEGER PRIMARY KEY CHECK (id = 1), dataset_id TEXT NOT NULL, metadata_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS donors (
  id INTEGER PRIMARY KEY, cohort_id TEXT, population TEXT, consent_json TEXT,
  family_id INTEGER, withdrawn_at TEXT
);
CREATE TABLE IF NOT EXISTS genotypes (
  donor_id INTEGER PRIMARY KEY REFERENCES donors(id) ON DELETE CASCADE, genotype_blob BYTEA
);
CREATE TABLE IF NOT EXISTS variants (
  id INTEGER PRIMARY KEY, chrom TEXT, pos INTEGER, ref TEXT, alt TEXT,
  maf DOUBLE PRECISION, is_rare INTEGER, planted INTEGER
);
CREATE TABLE IF NOT EXISTS relationships (
  id BIGSERIAL PRIMARY KEY, donor_a INTEGER, donor_b INTEGER, relation TEXT,
  meioses INTEGER, shared_fraction DOUBLE PRECISION
);
CREATE TABLE IF NOT EXISTS requesters (
  id BIGSERIAL PRIMARY KEY, name TEXT, role TEXT, credential_level TEXT, institution TEXT,
  api_key_hash TEXT UNIQUE, created_at TEXT, frozen_at TEXT
);
CREATE TABLE IF NOT EXISTS requests (
  id BIGSERIAL PRIMARY KEY, requester_id BIGINT NOT NULL REFERENCES requesters(id),
  ts TEXT, purpose TEXT, disease TEXT, is_commercial INTEGER, data_level TEXT,
  cohort_filter_json TEXT, variant_filter_json TEXT, status TEXT
);
CREATE INDEX IF NOT EXISTS requests_requester_id_id ON requests(requester_id, id DESC);
CREATE TABLE IF NOT EXISTS decisions (
  id BIGSERIAL PRIMARY KEY,
  request_id BIGINT NOT NULL UNIQUE REFERENCES requests(id) ON DELETE CASCADE,
  outcome TEXT, reasons_json TEXT, risk_json TEXT, transform_json TEXT, explanation_text TEXT,
  needs_human INTEGER, reviewed_by TEXT, reviewed_at TEXT, private_json TEXT, release_json TEXT
);
CREATE TABLE IF NOT EXISTS epsilon_ledger (
  requester_id BIGINT NOT NULL REFERENCES requesters(id), dataset_id TEXT NOT NULL,
  epsilon_spent DOUBLE PRECISION NOT NULL, updated_at TEXT,
  PRIMARY KEY(requester_id, dataset_id)
);
CREATE TABLE IF NOT EXISTS audit_log (
  idx BIGINT PRIMARY KEY, ts TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
  payload_json TEXT NOT NULL, prev_hash TEXT NOT NULL, hash TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS donor_access (
  id BIGSERIAL PRIMARY KEY, donor_id INTEGER NOT NULL REFERENCES donors(id) ON DELETE CASCADE,
  request_id BIGINT REFERENCES requests(id), ts TEXT, purpose TEXT, disease TEXT,
  level TEXT, institution TEXT
);
CREATE INDEX IF NOT EXISTS donor_access_donor ON donor_access(donor_id);
CREATE TABLE IF NOT EXISTS alerts (
  id BIGSERIAL PRIMARY KEY, requester_id BIGINT REFERENCES requesters(id),
  ts TEXT, kind TEXT, score DOUBLE PRECISION, details_json TEXT, action_taken TEXT
);
CREATE INDEX IF NOT EXISTS alerts_requester_id_id ON alerts(requester_id, id DESC);

-- Mark the same migration version as the Python adapter so it will not rerun DDL.
INSERT INTO schema_migrations(version) VALUES (1) ON CONFLICT (version) DO NOTHING;

-- Keep the schema private from PostgREST roles. The Python backend's server-side database
-- connection uses its own privileged database credentials; do not expose genomic tables.
