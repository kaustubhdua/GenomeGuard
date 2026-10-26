-- Non-sensitive deployment status used only by the server-side Edge Function.
-- Public/browser roles receive no table privileges; RLS is enabled as defense in depth.
CREATE TABLE IF NOT EXISTS public.genomeguard_deployment_status (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  api_migration_complete BOOLEAN NOT NULL DEFAULT FALSE,
  genomic_dataset_loaded BOOLEAN NOT NULL DEFAULT FALSE,
  render_dependency_present BOOLEAN NOT NULL DEFAULT TRUE,
  release_gate_passed BOOLEAN NOT NULL DEFAULT FALSE,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  notes TEXT NOT NULL
);
ALTER TABLE public.genomeguard_deployment_status ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.genomeguard_deployment_status FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE public.genomeguard_deployment_status TO service_role;
INSERT INTO public.genomeguard_deployment_status
  (id, api_migration_complete, genomic_dataset_loaded, render_dependency_present, release_gate_passed, notes)
VALUES
  (1, FALSE, FALSE, TRUE, FALSE,
   'Supabase schema is provisioned, but the Python API, cohort data, and endpoint parity have not been migrated.')
ON CONFLICT (id) DO UPDATE SET
  api_migration_complete = EXCLUDED.api_migration_complete,
  genomic_dataset_loaded = EXCLUDED.genomic_dataset_loaded,
  render_dependency_present = EXCLUDED.render_dependency_present,
  release_gate_passed = EXCLUDED.release_gate_passed,
  updated_at = now(),
  notes = EXCLUDED.notes;
