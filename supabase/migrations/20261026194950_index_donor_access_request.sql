-- Cover the request foreign key for request-scoped access-history lookups.
CREATE INDEX IF NOT EXISTS donor_access_request_id_idx
  ON genomeguard.donor_access(request_id)
  WHERE request_id IS NOT NULL;
