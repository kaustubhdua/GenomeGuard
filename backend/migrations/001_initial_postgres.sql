-- GenomeGuard PostgreSQL schema, version 1.
-- Apply only through app.postgres_store.PostgresStore; all DDL runs in one transaction.
CREATE TABLE cohort_metadata (
  id INTEGER PRIMARY KEY CHECK (id = 1), dataset_id TEXT NOT NULL, metadata_json TEXT NOT NULL
);
CREATE TABLE donors (
  id INTEGER PRIMARY KEY, cohort_id TEXT, population TEXT, consent_json TEXT,
  family_id INTEGER, withdrawn_at TEXT
);
CREATE TABLE genotypes (donor_id INTEGER PRIMARY KEY REFERENCES donors(id) ON DELETE CASCADE, genotype_blob BYTEA);
CREATE TABLE variants (
  id INTEGER PRIMARY KEY, chrom TEXT, pos INTEGER, ref TEXT, alt TEXT,
  maf DOUBLE PRECISION, is_rare INTEGER, planted INTEGER
);
CREATE TABLE relationships (
  id BIGSERIAL PRIMARY KEY, donor_a INTEGER, donor_b INTEGER, relation TEXT,
  meioses INTEGER, shared_fraction DOUBLE PRECISION
);
CREATE TABLE requesters (
  id BIGSERIAL PRIMARY KEY, name TEXT, role TEXT, credential_level TEXT, institution TEXT,
  api_key_hash TEXT UNIQUE, created_at TEXT, frozen_at TEXT
);
CREATE TABLE requests (
  id BIGSERIAL PRIMARY KEY, requester_id BIGINT NOT NULL REFERENCES requesters(id),
  ts TEXT, purpose TEXT, disease TEXT, is_commercial INTEGER, data_level TEXT,
  cohort_filter_json TEXT, variant_filter_json TEXT, status TEXT
);
CREATE INDEX requests_requester_id_id ON requests(requester_id, id DESC);
CREATE TABLE decisions (
  request_id BIGINT PRIMARY KEY REFERENCES requests(id) ON DELETE CASCADE,
  outcome TEXT, reasons_json TEXT, risk_json TEXT, transform_json TEXT, explanation_text TEXT,
  needs_human INTEGER, reviewed_by TEXT, reviewed_at TEXT, private_json TEXT, release_json TEXT
);
CREATE TABLE epsilon_ledger (
  requester_id BIGINT NOT NULL REFERENCES requesters(id), dataset_id TEXT NOT NULL,
  epsilon_spent DOUBLE PRECISION NOT NULL, updated_at TEXT,
  PRIMARY KEY(requester_id, dataset_id)
);
CREATE TABLE audit_log (
  idx BIGINT PRIMARY KEY, ts TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
  payload_json TEXT NOT NULL, prev_hash TEXT NOT NULL, hash TEXT NOT NULL UNIQUE
);
CREATE TABLE donor_access (
  id BIGSERIAL PRIMARY KEY, donor_id INTEGER NOT NULL REFERENCES donors(id) ON DELETE CASCADE,
  request_id BIGINT REFERENCES requests(id), ts TEXT, purpose TEXT, disease TEXT,
  level TEXT, institution TEXT
);
CREATE INDEX donor_access_donor ON donor_access(donor_id);
CREATE TABLE alerts (
  id BIGSERIAL PRIMARY KEY, requester_id BIGINT REFERENCES requesters(id),
  ts TEXT, kind TEXT, score DOUBLE PRECISION, details_json TEXT, action_taken TEXT
);
CREATE INDEX alerts_requester_id_id ON alerts(requester_id, id DESC);
