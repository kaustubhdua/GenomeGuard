-- ClinVar is a public archive of aggregate variant-level assertions, separate from cohort calls.
CREATE TABLE IF NOT EXISTS genomeguard.clinvar_annotation_manifest (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  dataset_key text NOT NULL UNIQUE CHECK (length(trim(dataset_key)) BETWEEN 3 AND 120),
  source_name text NOT NULL CHECK (length(trim(source_name)) BETWEEN 3 AND 200),
  source_url text NOT NULL CHECK (source_url ~ '^https://'),
  source_release text NOT NULL CHECK (length(trim(source_release)) BETWEEN 1 AND 120),
  reference_assembly text NOT NULL CHECK (reference_assembly IN ('GRCh37', 'GRCh38')),
  data_use_review text NOT NULL DEFAULT 'pending'
    CHECK (data_use_review IN ('pending', 'approved_public_research', 'rejected')),
  import_status text NOT NULL DEFAULT 'registered'
    CHECK (import_status IN ('registered', 'validated', 'loading', 'loaded', 'failed', 'retired')),
  file_sha256 text CHECK (file_sha256 IS NULL OR file_sha256 ~ '^[0-9a-f]{64}$'),
  annotation_row_count bigint NOT NULL DEFAULT 0 CHECK (annotation_row_count >= 0),
  imported_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT clinvar_loaded_requires_review CHECK (
    import_status <> 'loaded'
    OR (data_use_review = 'approved_public_research'
        AND annotation_row_count > 0 AND imported_at IS NOT NULL)
  )
);

CREATE TABLE IF NOT EXISTS genomeguard.clinvar_variant_annotation (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  dataset_id uuid NOT NULL REFERENCES genomeguard.clinvar_annotation_manifest(id),
  chromosome text NOT NULL CHECK (chromosome IN
    ('1','2','3','4','5','6','7','8','9','10','11','12','13','14','15','16','17','18','19','20','21','22','X','Y','MT')),
  position integer NOT NULL CHECK (position > 0),
  reference_allele text NOT NULL CHECK (reference_allele ~ '^[ACGTN]+$'),
  alternate_allele text NOT NULL CHECK (alternate_allele ~ '^[ACGTN]+$'),
  variation_id bigint NOT NULL CHECK (variation_id > 0),
  clinical_significance text NOT NULL CHECK (length(clinical_significance) <= 500),
  review_status text NOT NULL CHECK (length(review_status) <= 500),
  last_evaluated date,
  conditions jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(conditions) = 'array'),
  gene_symbols jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(gene_symbols) = 'array'),
  submitter_count integer CHECK (submitter_count IS NULL OR submitter_count >= 0),
  UNIQUE (dataset_id, chromosome, position, reference_allele, alternate_allele, variation_id),
  CHECK (reference_allele <> alternate_allele),
  CHECK (length(reference_allele) = length(alternate_allele))
);

COMMENT ON TABLE genomeguard.clinvar_variant_annotation IS
  'Variant-level ClinVar summary assertions, not patient diagnoses or sample-level genotype data.';
CREATE INDEX IF NOT EXISTS clinvar_variant_annotation_locus_idx
  ON genomeguard.clinvar_variant_annotation
  (chromosome, position, reference_allele, alternate_allele, dataset_id);

ALTER TABLE genomeguard.clinvar_annotation_manifest ENABLE ROW LEVEL SECURITY;
ALTER TABLE genomeguard.clinvar_variant_annotation ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON genomeguard.clinvar_annotation_manifest FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON genomeguard.clinvar_variant_annotation FROM PUBLIC, anon, authenticated, service_role;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'genomeguard_clinvar_importer') THEN
    CREATE ROLE genomeguard_clinvar_importer NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'genomeguard_clinvar_reader') THEN
    CREATE ROLE genomeguard_clinvar_reader NOLOGIN;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    EXECUTE 'GRANT genomeguard_clinvar_reader TO service_role';
  END IF;
END
$$;

CREATE POLICY clinvar_manifest_importer_read
  ON genomeguard.clinvar_annotation_manifest
  FOR SELECT TO genomeguard_clinvar_importer USING (true);
CREATE POLICY clinvar_annotation_importer_read
  ON genomeguard.clinvar_variant_annotation
  FOR SELECT TO genomeguard_clinvar_importer USING (true);
CREATE POLICY clinvar_annotation_importer_insert
  ON genomeguard.clinvar_variant_annotation
  FOR INSERT TO genomeguard_clinvar_importer WITH CHECK (true);

CREATE POLICY clinvar_manifest_reader_select
  ON genomeguard.clinvar_annotation_manifest
  FOR SELECT TO genomeguard_clinvar_reader
  USING (data_use_review = 'approved_public_research' AND import_status = 'loaded');
CREATE POLICY clinvar_annotation_reader_select
  ON genomeguard.clinvar_variant_annotation
  FOR SELECT TO genomeguard_clinvar_reader
  USING (EXISTS (
    SELECT 1
    FROM genomeguard.clinvar_annotation_manifest AS m
    WHERE m.id = dataset_id
      AND m.data_use_review = 'approved_public_research'
      AND m.import_status = 'loaded'
  ));

GRANT USAGE ON SCHEMA genomeguard TO genomeguard_clinvar_importer, genomeguard_clinvar_reader;
GRANT SELECT ON genomeguard.clinvar_annotation_manifest TO genomeguard_clinvar_importer, genomeguard_clinvar_reader;
GRANT SELECT, INSERT ON genomeguard.clinvar_variant_annotation TO genomeguard_clinvar_importer;
GRANT SELECT ON genomeguard.clinvar_variant_annotation TO genomeguard_clinvar_reader;
GRANT USAGE, SELECT ON SEQUENCE genomeguard.clinvar_variant_annotation_id_seq TO genomeguard_clinvar_importer;

