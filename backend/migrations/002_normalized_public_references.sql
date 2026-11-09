-- Native PostgreSQL schema for GenomeGuard's normalized public reference data.
-- Independent of Supabase, PostgREST, Auth, provider roles, and RLS.
CREATE SCHEMA IF NOT EXISTS genomeguard;

CREATE TABLE IF NOT EXISTS genomeguard.variant_dataset_manifest (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 dataset_key text NOT NULL UNIQUE CHECK (length(trim(dataset_key)) BETWEEN 3 AND 120),
 source_name text NOT NULL CHECK (length(trim(source_name)) BETWEEN 3 AND 200),
 source_url text NOT NULL CHECK (source_url ~ '^https://'),
 source_release text NOT NULL,
 reference_assembly text NOT NULL CHECK (reference_assembly IN ('GRCh37','GRCh38','T2T-CHM13')),
 file_sha256 text NOT NULL CHECK (file_sha256 ~ '^[0-9a-f]{64}$'),
 data_use_review text NOT NULL CHECK (data_use_review IN ('pending','approved_public_research','approved_controlled_access','rejected')),
 consent_basis text NOT NULL CHECK (consent_basis IN ('dataset_policy','verified_participant_records','not_applicable')),
 import_status text NOT NULL DEFAULT 'registered' CHECK (import_status IN ('registered','validated','loading','loaded','failed','retired')),
 variant_count bigint NOT NULL DEFAULT 0 CHECK (variant_count >= 0),
 genotype_call_count bigint NOT NULL DEFAULT 0 CHECK (genotype_call_count >= 0),
 sample_count integer NOT NULL DEFAULT 0 CHECK (sample_count >= 0),
 imported_at timestamptz,
 metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 CHECK (import_status <> 'loaded' OR (variant_count > 0 AND sample_count > 0 AND genotype_call_count > 0 AND imported_at IS NOT NULL)),
 CHECK (import_status <> 'loaded' OR data_use_review IN ('approved_public_research','approved_controlled_access'))
);

CREATE TABLE IF NOT EXISTS genomeguard.dataset_samples (
 id bigserial PRIMARY KEY,
 dataset_id uuid NOT NULL REFERENCES genomeguard.variant_dataset_manifest(id) ON DELETE RESTRICT,
 source_sample_id text NOT NULL CHECK (length(trim(source_sample_id)) BETWEEN 1 AND 200),
 population text,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (dataset_id, source_sample_id),
 UNIQUE (dataset_id, id)
);

CREATE TABLE IF NOT EXISTS genomeguard.dataset_variants (
 id bigserial PRIMARY KEY,
 dataset_id uuid NOT NULL REFERENCES genomeguard.variant_dataset_manifest(id) ON DELETE RESTRICT,
 variant_index bigint NOT NULL CHECK (variant_index >= 0),
 variant_key text NOT NULL,
 chromosome text NOT NULL CHECK (chromosome ~ '^(chr)?([0-9]{1,2}|X|Y|M|MT)$'),
 position integer NOT NULL CHECK (position > 0),
 reference_allele text NOT NULL CHECK (reference_allele ~ '^[ACGTN]+$'),
 alternate_allele text NOT NULL CHECK (alternate_allele ~ '^[ACGTN]+$'),
 alt_allele_frequency double precision CHECK (alt_allele_frequency >= 0 AND alt_allele_frequency <= 1),
 called_allele_count bigint NOT NULL DEFAULT 0 CHECK (called_allele_count >= 0),
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (dataset_id, variant_index),
 UNIQUE (dataset_id, variant_key),
 UNIQUE (dataset_id, id),
 CHECK (reference_allele <> alternate_allele)
);
CREATE INDEX IF NOT EXISTS dataset_variants_dataset_chrom_pos ON genomeguard.dataset_variants(dataset_id, chromosome, position);

CREATE TABLE IF NOT EXISTS genomeguard.dataset_genotype_calls (
 dataset_id uuid NOT NULL REFERENCES genomeguard.variant_dataset_manifest(id) ON DELETE RESTRICT,
 sample_id bigint NOT NULL,
 variant_id bigint NOT NULL,
 alt_dosage smallint CHECK (alt_dosage IN (0,1,2)),
 called_alleles smallint NOT NULL CHECK (called_alleles IN (0,1,2)),
 phased boolean NOT NULL DEFAULT false,
 source_record_index bigint NOT NULL CHECK (source_record_index >= 0),
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (dataset_id, sample_id, variant_id),
 FOREIGN KEY (dataset_id, sample_id) REFERENCES genomeguard.dataset_samples(dataset_id, id) ON DELETE RESTRICT,
 FOREIGN KEY (dataset_id, variant_id) REFERENCES genomeguard.dataset_variants(dataset_id, id) ON DELETE RESTRICT,
 CHECK ((called_alleles = 0 AND alt_dosage IS NULL) OR (called_alleles > 0 AND alt_dosage IS NOT NULL AND alt_dosage <= called_alleles))
);
CREATE INDEX IF NOT EXISTS dataset_genotype_calls_variant ON genomeguard.dataset_genotype_calls(dataset_id, variant_id);
CREATE INDEX IF NOT EXISTS dataset_genotype_calls_sample ON genomeguard.dataset_genotype_calls(dataset_id, sample_id);

-- Aggregate population frequencies are separate from individual genotype calls.
CREATE TABLE IF NOT EXISTS genomeguard.population_reference_manifest (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 dataset_key text NOT NULL UNIQUE CHECK (length(trim(dataset_key)) BETWEEN 3 AND 120),
 source_name text NOT NULL CHECK (length(trim(source_name)) BETWEEN 3 AND 200),
 source_url text NOT NULL CHECK (source_url ~ '^https://'),
 source_release text NOT NULL,
 reference_assembly text NOT NULL CHECK (reference_assembly IN ('GRCh37','GRCh38')),
 represented_individual_count integer NOT NULL CHECK (represented_individual_count >= 0),
 data_use_review text NOT NULL DEFAULT 'pending' CHECK (data_use_review IN ('pending','approved_public_research','rejected')),
 import_status text NOT NULL DEFAULT 'registered' CHECK (import_status IN ('registered','validated','loading','loaded','failed','retired')),
 file_sha256 text CHECK (file_sha256 IS NULL OR file_sha256 ~ '^[0-9a-f]{64}$'),
 variant_population_row_count bigint NOT NULL DEFAULT 0 CHECK (variant_population_row_count >= 0),
 metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
 imported_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(),
 CHECK (import_status <> 'loaded' OR (data_use_review = 'approved_public_research' AND variant_population_row_count > 0 AND imported_at IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS genomeguard.population_variant_frequency (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 dataset_id uuid NOT NULL REFERENCES genomeguard.population_reference_manifest(id) ON DELETE RESTRICT,
 chromosome text NOT NULL CHECK (chromosome IN ('1','2','3','4','5','6','7','8','9','10','11','12','13','14','15','16','17','18','19','20','21','22','X','Y','MT')),
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
CREATE INDEX IF NOT EXISTS population_variant_frequency_locus_idx ON genomeguard.population_variant_frequency(chromosome, position, reference_allele, alternate_allele, dataset_id);
CREATE INDEX IF NOT EXISTS population_reference_manifest_approved_idx ON genomeguard.population_reference_manifest(data_use_review, import_status, reference_assembly);
