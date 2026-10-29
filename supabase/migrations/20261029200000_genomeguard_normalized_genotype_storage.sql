-- Normalized, provenance-linked public research data model for the VCF importer.
-- This migration creates empty tables only; it imports no data and grants no browser access.
create table if not exists genomeguard.dataset_samples (
  id bigserial primary key,
  dataset_id uuid not null references genomeguard.variant_dataset_manifest(id) on delete restrict,
  source_sample_id text not null check (length(trim(source_sample_id)) between 1 and 200),
  population text,
  created_at timestamptz not null default now(),
  unique (dataset_id, source_sample_id),
  unique (dataset_id, id)
);

create table if not exists genomeguard.dataset_variants (
  id bigserial primary key,
  dataset_id uuid not null references genomeguard.variant_dataset_manifest(id) on delete restrict,
  variant_index bigint not null check (variant_index >= 0),
  variant_key text not null,
  chromosome text not null check (chromosome ~ '^(chr)?([0-9]{1,2}|X|Y|M|MT)$'),
  position integer not null check (position > 0),
  reference_allele text not null check (reference_allele ~ '^[ACGTN]+$'),
  alternate_allele text not null check (alternate_allele ~ '^[ACGTN]+$'),
  alt_allele_frequency double precision check (alt_allele_frequency >= 0 and alt_allele_frequency <= 1),
  called_allele_count bigint not null default 0 check (called_allele_count >= 0),
  created_at timestamptz not null default now(),
  unique (dataset_id, variant_index),
  unique (dataset_id, variant_key),
  unique (dataset_id, id)
);
create index if not exists dataset_variants_dataset_chrom_pos
  on genomeguard.dataset_variants(dataset_id, chromosome, position);

-- One row per sample × split alternate allele. Dosage is 0, 1, or 2 copies of that
-- ALT allele; missing calls have null dosage and called_alleles=0. Multi-allelic VCF
-- records are split into one variant per ALT, preserving the original source record index.
create table if not exists genomeguard.dataset_genotype_calls (
  dataset_id uuid not null references genomeguard.variant_dataset_manifest(id) on delete restrict,
  sample_id bigint not null,
  variant_id bigint not null,
  alt_dosage smallint check (alt_dosage in (0,1,2)),
  called_alleles smallint not null check (called_alleles in (0,1,2)),
  phased boolean not null default false,
  source_record_index bigint not null check (source_record_index >= 0),
  created_at timestamptz not null default now(),
  primary key (dataset_id, sample_id, variant_id),
  foreign key (dataset_id, sample_id)
    references genomeguard.dataset_samples(dataset_id, id) on delete restrict,
  foreign key (dataset_id, variant_id)
    references genomeguard.dataset_variants(dataset_id, id) on delete restrict,
  check ((called_alleles = 0 and alt_dosage is null) or
         (called_alleles > 0 and alt_dosage is not null and alt_dosage <= called_alleles))
);
create index if not exists dataset_genotype_calls_variant
  on genomeguard.dataset_genotype_calls(dataset_id, variant_id);
create index if not exists dataset_genotype_calls_sample
  on genomeguard.dataset_genotype_calls(dataset_id, sample_id);

alter table genomeguard.dataset_samples enable row level security;
alter table genomeguard.dataset_variants enable row level security;
alter table genomeguard.dataset_genotype_calls enable row level security;
revoke all on table genomeguard.dataset_samples from public, anon, authenticated, service_role;
revoke all on table genomeguard.dataset_variants from public, anon, authenticated, service_role;
revoke all on table genomeguard.dataset_genotype_calls from public, anon, authenticated, service_role;

comment on table genomeguard.dataset_genotype_calls is
  'Private normalized genotype calls tied to a manifest dataset. No direct browser access; release must be governed by verified consent and policy.';
