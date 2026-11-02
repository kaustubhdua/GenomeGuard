-- A non-login role for the trusted VCF import process. Browser and Edge Function
-- service roles receive no direct grants to these tables.
do $role$
begin
  if not exists (select 1 from pg_roles where rolname = 'genomeguard_importer') then
    create role genomeguard_importer nologin noinherit;
  end if;
end
$role$;

grant usage on schema genomeguard to genomeguard_importer;
grant select on genomeguard.variant_dataset_manifest to genomeguard_importer;
grant update (import_status, variant_count, genotype_call_count, sample_count, imported_at, updated_at, metadata)
  on genomeguard.variant_dataset_manifest to genomeguard_importer;

grant select, insert, delete on genomeguard.dataset_samples to genomeguard_importer;
grant select, insert, delete on genomeguard.dataset_variants to genomeguard_importer;
grant select, insert, delete on genomeguard.dataset_genotype_calls to genomeguard_importer;
grant usage, select on sequence genomeguard.dataset_samples_id_seq to genomeguard_importer;
grant usage, select on sequence genomeguard.dataset_variants_id_seq to genomeguard_importer;

revoke all on genomeguard.variant_dataset_manifest from public, anon, authenticated, service_role;
revoke all on genomeguard.dataset_samples from public, anon, authenticated, service_role;
revoke all on genomeguard.dataset_variants from public, anon, authenticated, service_role;
revoke all on genomeguard.dataset_genotype_calls from public, anon, authenticated, service_role;

-- Supabase's trusted postgres connection can explicitly SET ROLE for the importer session.
-- No browser, anon, authenticated, or service_role membership is granted.

-- RLS is enabled and default-deny. Give the importer explicit policies limited to
-- approved public-research manifests while their status is loading.
drop policy if exists gg_importer_manifest_select on genomeguard.variant_dataset_manifest;
create policy gg_importer_manifest_select on genomeguard.variant_dataset_manifest
  for select to genomeguard_importer
  using (data_use_review = 'approved_public_research');

drop policy if exists gg_importer_manifest_update on genomeguard.variant_dataset_manifest;
create policy gg_importer_manifest_update on genomeguard.variant_dataset_manifest
  for update to genomeguard_importer
  using (data_use_review = 'approved_public_research' and import_status <> 'loaded')
  with check (data_use_review = 'approved_public_research');

drop policy if exists gg_importer_samples_all on genomeguard.dataset_samples;
create policy gg_importer_samples_all on genomeguard.dataset_samples
  for all to genomeguard_importer
  using (exists (
    select 1 from genomeguard.variant_dataset_manifest m
    where m.id = dataset_id and m.data_use_review = 'approved_public_research'
      and m.import_status = 'loading'
  ))
  with check (exists (
    select 1 from genomeguard.variant_dataset_manifest m
    where m.id = dataset_id and m.data_use_review = 'approved_public_research'
      and m.import_status = 'loading'
  ));

drop policy if exists gg_importer_variants_all on genomeguard.dataset_variants;
create policy gg_importer_variants_all on genomeguard.dataset_variants
  for all to genomeguard_importer
  using (exists (
    select 1 from genomeguard.variant_dataset_manifest m
    where m.id = dataset_id and m.data_use_review = 'approved_public_research'
      and m.import_status = 'loading'
  ))
  with check (exists (
    select 1 from genomeguard.variant_dataset_manifest m
    where m.id = dataset_id and m.data_use_review = 'approved_public_research'
      and m.import_status = 'loading'
  ));

drop policy if exists gg_importer_calls_all on genomeguard.dataset_genotype_calls;
create policy gg_importer_calls_all on genomeguard.dataset_genotype_calls
  for all to genomeguard_importer
  using (exists (
    select 1 from genomeguard.variant_dataset_manifest m
    where m.id = dataset_id and m.data_use_review = 'approved_public_research'
      and m.import_status = 'loading'
  ))
  with check (exists (
    select 1 from genomeguard.variant_dataset_manifest m
    where m.id = dataset_id and m.data_use_review = 'approved_public_research'
      and m.import_status = 'loading'
  ));

grant genomeguard_importer to postgres;
comment on role genomeguard_importer is
  'Least-privilege, NOLOGIN role for a trusted operator running the GenomeGuard VCF importer after a separate source-review approval.';