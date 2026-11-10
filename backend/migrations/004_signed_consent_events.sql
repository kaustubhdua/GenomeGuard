-- Source-sample mapping and append-only, signed consent-change event ledger.
ALTER TABLE donors ADD COLUMN IF NOT EXISTS source_sample_id_hash TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS donors_source_sample_id_hash_unique
  ON donors(source_sample_id_hash) WHERE source_sample_id_hash IS NOT NULL;

CREATE TABLE IF NOT EXISTS consent_events (
  event_id TEXT PRIMARY KEY,
  donor_id INTEGER NOT NULL REFERENCES donors(id) ON DELETE RESTRICT,
  dataset_id TEXT NOT NULL,
  event_type TEXT NOT NULL CHECK (event_type IN ('consent_updated','withdrawn','restored')),
  consent_blob BYTEA NOT NULL,
  source_issuer TEXT NOT NULL,
  source_record_sha256 TEXT NOT NULL CHECK (source_record_sha256 ~ '^[0-9a-f]{64}$'),
  effective_at TEXT NOT NULL,
  received_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS consent_events_donor_effective
  ON consent_events(donor_id, effective_at DESC);
COMMENT ON TABLE consent_events IS
  'Append-only record of externally signed participant consent changes; never a substitute for source-system governance.';
