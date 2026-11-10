-- Organization-bound identities and tenant labels for requester-scoped research activity.
-- The application still requires explicit authorization on every API request; this migration
-- supplies durable identity bindings and tenant keys, not an automatic legal approval.
ALTER TABLE requesters ADD COLUMN IF NOT EXISTS organization_id TEXT;
ALTER TABLE requests ADD COLUMN IF NOT EXISTS organization_id TEXT;

CREATE TABLE IF NOT EXISTS identity_bindings (
  issuer TEXT NOT NULL,
  subject TEXT NOT NULL,
  organization_id TEXT NOT NULL,
  requester_id INTEGER NOT NULL REFERENCES requesters(id) ON DELETE CASCADE,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TEXT NOT NULL,
  revoked_at TEXT,
  PRIMARY KEY (issuer, subject, organization_id),
  CHECK (length(trim(issuer)) > 0),
  CHECK (length(trim(subject)) BETWEEN 1 AND 255),
  CHECK (length(trim(organization_id)) BETWEEN 1 AND 255)
);
CREATE INDEX IF NOT EXISTS identity_bindings_requester_active
  ON identity_bindings(requester_id, active);
CREATE INDEX IF NOT EXISTS requests_organization_requester
  ON requests(organization_id, requester_id, id DESC);

COMMENT ON TABLE identity_bindings IS
  'Operator-provisioned mapping from a verified OIDC issuer/subject/org tuple to a GenomeGuard requester.';
COMMENT ON COLUMN requests.organization_id IS
  'Organization ID taken from the verified identity binding, never from a client-supplied request field.';
