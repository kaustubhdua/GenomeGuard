-- The participant consent ledger is append-only for application/runtime roles.
CREATE OR REPLACE FUNCTION genomeguard_reject_consent_event_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'consent_events is append-only; create a superseding signed event';
END;
$$;

DROP TRIGGER IF EXISTS consent_events_immutable ON consent_events;
CREATE TRIGGER consent_events_immutable
BEFORE UPDATE OR DELETE ON consent_events
FOR EACH ROW EXECUTE FUNCTION genomeguard_reject_consent_event_mutation();
