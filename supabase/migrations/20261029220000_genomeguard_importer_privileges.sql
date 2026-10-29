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

revoke all on schema genomeguard from public, anon, authenticated, service_role;
revoke all on genomeguard.variant_dataset_manifest from public, anon, authenticated, service_role;
revoke all on genomeguard.dataset_samples from public, anon, authenticated, service_role;
revoke all on genomeguard.dataset_variants from public, anon, authenticated, service_role;
revoke all on genomeguard.dataset_genotype_calls from public, anon, authenticated, service_role;

-- Supabase's trusted postgres connection can explicitly SET ROLE for the importer session.
-- No browser, anon, authenticated, or service_role membership is granted.
grant genomeguard_importer to postgres;
comment on role genomeguard_importer is
  'Least-privilege, NOLOGIN role for a trusted operator running the GenomeGuard VCF importer after a separate source-review approval.';
