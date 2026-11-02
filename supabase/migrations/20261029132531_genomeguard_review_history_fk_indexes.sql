-- Cover foreign-key lookups on the append-only review history table.
-- These indexes improve joins and referential checks without changing authorization semantics.
CREATE INDEX IF NOT EXISTS request_review_history_decision_id_idx
  ON genomeguard.request_review_history(decision_id);

CREATE INDEX IF NOT EXISTS request_review_history_organization_id_idx
  ON genomeguard.request_review_history(organization_id);