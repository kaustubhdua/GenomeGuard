-- Expose only fully loaded, explicitly reviewed public-research datasets.
-- The underlying manifest remains private; callers cannot read or mutate it directly.
create or replace function public.gg_list_verified_public_datasets()
returns table (
  dataset_key text,
  source_name text,
  source_url text,
  source_release text,
  reference_assembly text,
  file_sha256 text,
  variant_count bigint,
  genotype_call_count bigint,
  sample_count integer,
  imported_at timestamptz
)
language sql
stable
security definer
set search_path = ''
as $$
  select
    m.dataset_key,
    m.source_name,
    m.source_url,
    m.source_release,
    m.reference_assembly,
    m.file_sha256,
    m.variant_count,
    m.genotype_call_count,
    m.sample_count,
    m.imported_at
  from genomeguard.variant_dataset_manifest as m
  where m.data_use_review = 'approved_public_research'
    and m.import_status = 'loaded'
    and m.variant_count > 0
    and m.genotype_call_count > 0
    and m.sample_count > 0
    and m.imported_at is not null
  order by m.source_name, m.dataset_key;
$$;

revoke all on function public.gg_list_verified_public_datasets() from public, anon, authenticated;
grant execute on function public.gg_list_verified_public_datasets() to service_role;

comment on function public.gg_list_verified_public_datasets() is
  'Returns only manifest entries explicitly reviewed for public research and marked loaded with non-zero measured counts. Does not establish participant-specific consent or clinical suitability.';
