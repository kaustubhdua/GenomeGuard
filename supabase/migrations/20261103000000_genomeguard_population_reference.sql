-- Aggregate population reference data is NOT individual-level genotype data.
-- Keep it separate from dataset_samples / dataset_genotype_calls and the VCF cohort importer.
CREATE TABLE IF NOT EXISTS genomeguard.population_reference_manifest (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  dataset_key text NOT NULL UNIQUE CHECK (length(trim(dataset_key)) BETWEEN 3 AND 120),
  source_name text NOT NULL CHECK (length(trim(source_name)) BETWEEN 3 AND 200),
  source_url text NOT NULL CHECK (source_url ~ '^https://'),
  source_release text NOT NULL CHECK (length(trim(source_release)) BETWEEN 1 AND 120),
  reference_assembly text NOT NULL CHECK (reference_assembly IN ('GRCh37', 'GRCh38')),
  represented_individual_count integer NOT NULL CHECK (represented_individual_count >= 100000),
  data_use_review text NOT NULL DEFAULT 'pending'
    CHECK (data_use_review IN ('pending', 'approved_public_research', 'rejected')),
  import_status text NOT NULL DEFAULT 'registered'
    CHECK (import_status IN ('registered', 'validated', 'loading', 'loaded', 'failed', 'retired')),
  file_sha256 text CHECK (file_sha256 IS NULL OR file_sha256 ~ '^[0-9a-f]{64}$'),
  variant_population_row_count bigint NOT NULL DEFAULT 0 CHECK (variant_population_row_count >= 0),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  imported_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT population_reference_loaded_requires_review CHECK (
    import_status <> 'loaded'
    OR (data_use_review = 'approved_public_research'
        AND variant_population_row_count > 0 AND imported_at IS NOT NULL)
  )
);

CREATE TABLE IF NOT EXISTS genomeguard.population_variant_frequency (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  dataset_id uuid NOT NULL REFERENCES genomeguard.population_reference_manifest(id),
  chromosome text NOT NULL CHECK (chromosome IN
    ('1','2','3','4','5','6','7','8','9','10','11','12','13','14','15','16','17','18','19','20','21','22','X','Y','MT')),
  position integer NOT NULL CHECK (position > 0),
  reference_allele text NOT NULL CHECK (reference_allele ~ '^[ACGTN]+$'),
  alternate_allele text NOT NULL CHECK (alternate_allele ~ '^[ACGTN]+$'),
  population text NOT NULL CHECK (length(trim(population)) BETWEEN 1 AND 80),
  allele_count bigint NOT NULL CHECK (allele_count >= 0),
  allele_number bigint NOT NULL CHECK (allele_number >= allele_count),
  allele_frequency double precision NOT NULL CHECK (allele_frequency BETWEEN 0 AND 1),
  homozygote_count bigint CHECK (homozygote_count IS NULL OR homozygote_count >= 0),
  UNIQUE (dataset_id, chromosome, position, reference_allele, alternate_allele, population),
  CHECK (reference_allele <> alternate_allele),
  CHECK (allele_number > 0)
);

COMMENT ON TABLE genomeguard.population_reference_manifest IS
  'Provenance ledger for aggregate population-frequency references (for example gnomAD); represented_individual_count is source cohort size, not locally stored people.';
COMMENT ON TABLE genomeguard.population_variant_frequency IS
  'Aggregate allele counts/frequencies by population. Contains no participant identifiers, individual genotypes, or sample-level calls.';
COMMENT ON COLUMN genomeguard.population_reference_manifest.represented_individual_count IS
  'Number of individuals represented by the upstream aggregate reference; does not mean individual-level records are available or imported.';

ALTER TABLE genomeguard.population_reference_manifest ENABLE ROW LEVEL SECURITY;
ALTER TABLE genomeguard.population_variant_frequency ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON genomeguard.population_reference_manifest FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON genomeguard.population_variant_frequency FROM PUBLIC, anon, authenticated, service_role;

-- Dedicated append-only import role. Dataset approval/status changes remain a steward operation.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'genomeguard_reference_importer') THEN
    CREATE ROLE genomeguard_reference_importer NOLOGIN;
  END IF;
END
$$;

CREATE POLICY population_reference_manifest_importer_read
  ON genomeguard.population_reference_manifest
  FOR SELECT TO genomeguard_reference_importer USING (true);
CREATE POLICY population_variant_frequency_importer_read
  ON genomeguard.population_variant_frequency
  FOR SELECT TO genomeguard_reference_importer USING (true);
CREATE POLICY population_variant_frequency_importer_insert
  ON genomeguard.population_variant_frequency
  FOR INSERT TO genomeguard_reference_importer WITH CHECK (true);

GRANT USAGE ON SCHEMA genomeguard TO genomeguard_reference_importer;
GRANT SELECT ON genomeguard.population_reference_manifest TO genomeguard_reference_importer;
GRANT INSERT, SELECT ON genomeguard.population_variant_frequency TO genomeguard_reference_importer;
GRANT USAGE, SELECT ON SEQUENCE genomeguard.population_variant_frequency_id_seq TO genomeguard_reference_importer;
