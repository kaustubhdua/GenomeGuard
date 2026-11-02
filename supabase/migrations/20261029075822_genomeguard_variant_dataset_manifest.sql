-- Dataset-level provenance ledger. This records verified imports; it does not itself load or certify genotype data.
-- Keep all GenomeGuard objects isolated in the private schema shared project.
create table if not exists genomeguard.variant_dataset_manifest (
  id uuid primary key default gen_random_uuid(),
  dataset_key text not null unique check (length(trim(dataset_key)) between 3 and 120),
  source_name text not null check (length(trim(source_name)) between 3 and 200),
  source_url text not null check (source_url ~ '^https://'),
  source_release text not null check (length(trim(source_release)) between 1 and 120),
  reference_assembly text not null check (reference_assembly in ('GRCh37', 'GRCh38', 'T2T-CHM13')),
  file_sha256 text not null check (file_sha256 ~ '^[0-9a-f]{64}$'),
  data_use_review text not null check (data_use_review in ('pending', 'approved_public_research', 'approved_controlled_access', 'rejected')),
  consent_basis text not null check (consent_basis in ('dataset_policy', 'verified_participant_records', 'not_applicable')),
  import_status text not null default 'registered' check (import_status in ('registered', 'validated', 'loading', 'loaded', 'failed', 'retired')),
  variant_count bigint not null default 0 check (variant_count >= 0),
  genotype_call_count bigint not null default 0 check (genotype_call_count >= 0),
  sample_count integer not null default 0 check (sample_count >= 0),
  imported_at timestamptz,
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint dataset_loaded_requires_counts check (
    import_status <> 'loaded'
    or (variant_count > 0 and sample_count > 0 and genotype_call_count > 0 and imported_at is not null)
  ),
  constraint dataset_loaded_requires_review check (
    import_status <> 'loaded'
    or data_use_review in ('approved_public_research', 'approved_controlled_access')
  )
);

comment on table genomeguard.variant_dataset_manifest is
  'Server-only provenance and import ledger. A manifest row is not proof of valid consent or scientific validity; verify source terms and checksums independently.';
comment on column genomeguard.variant_dataset_manifest.file_sha256 is
  'SHA-256 of the exact source artifact used for import, lowercase hexadecimal.';
alter table genomeguard.variant_dataset_manifest enable row level security;
revoke all on table genomeguard.variant_dataset_manifest from public, anon, authenticated;
revoke all on table genomeguard.variant_dataset_manifest from service_role;
